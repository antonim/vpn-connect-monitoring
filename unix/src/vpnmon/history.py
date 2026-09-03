"""Журнал состояния и разбор его в отрезки для графика.

Формат и логика повторяют Windows-версию, чтобы журналы с обеих платформ
читались одинаково: строки ``ГГГГ-ММ-ДД ЧЧ:ММ:СС;состояние``.

Пишется не каждая проверка, а смена состояния плюс «сердцебиение» раз в
HEARTBEAT_MINUTES. Это держит файл компактным и позволяет отличить «связь
была всё время» от «программа не работала»: разрыв между соседними записями
больше GAP_MINUTES означает отсутствие наблюдения. Так выключение машины,
сон и аварийное завершение не превращаются в ложный зелёный участок.
"""

import datetime
import os
import threading

from . import config

UNKNOWN = "idle"
UP = "up"
DOWN = "down"

HEARTBEAT_MINUTES = 5
GAP_MINUTES = 12
RETENTION_DAYS = 30

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

HISTORY_PATH = os.path.join(config.CONFIG_DIR, "history.csv")

_lock = threading.Lock()
_last_write = None
_last_state = None


class Sample(object):
    __slots__ = ("time", "state")

    def __init__(self, time, state):
        self.time = time
        self.state = state


class Segment(object):
    __slots__ = ("start", "end", "state")

    def __init__(self, start, end, state):
        self.start = start
        self.end = end
        self.state = state

    @property
    def duration(self):
        return self.end - self.start


def record(now, state):
    """Записать состояние, если оно изменилось или истёк интервал сердцебиения."""
    global _last_write, _last_state

    with _lock:
        same = state == _last_state and _last_write is not None
        if same and (now - _last_write).total_seconds() < HEARTBEAT_MINUTES * 60:
            return

        try:
            os.makedirs(config.CONFIG_DIR, exist_ok=True)
            with open(HISTORY_PATH, "a", encoding="utf-8") as fh:
                fh.write("%s;%s\n" % (now.strftime(TIME_FORMAT), state))
            _last_write = now
            _last_state = state
        except OSError:
            # Журнал вспомогательный: сбой записи не должен ронять наблюдение.
            pass


def load(since):
    """Записи начиная с since плюс последняя перед ним.

    Без предыдущей записи неизвестно состояние на левой границе диапазона.
    """
    result = []
    before = None

    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return result

    for raw in lines:
        line = raw.strip()
        if not line or ";" not in line:
            continue
        stamp, _, state = line.partition(";")
        try:
            when = datetime.datetime.strptime(stamp, TIME_FORMAT)
        except ValueError:
            continue

        state = state.strip().lower()
        if state not in (UP, DOWN, UNKNOWN):
            state = UNKNOWN

        sample = Sample(when, state)
        if when < since:
            before = sample
        else:
            result.append(sample)

    if before is not None:
        result.insert(0, before)
    return result


def prune():
    try:
        if not os.path.exists(HISTORY_PATH):
            return
        cutoff = datetime.datetime.now() - datetime.timedelta(days=RETENTION_DAYS)

        with open(HISTORY_PATH, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

        keep = []
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            stamp = line.partition(";")[0]
            try:
                if datetime.datetime.strptime(stamp, TIME_FORMAT) < cutoff:
                    continue
            except ValueError:
                pass
            keep.append(line)

        if len(keep) != len([l for l in lines if l.strip()]):
            tmp = HISTORY_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write("\n".join(keep) + ("\n" if keep else ""))
            os.replace(tmp, HISTORY_PATH)
    except OSError:
        pass


def build_segments(samples, since, until):
    """Разворачивает точечные записи в непрерывную ленту без пропусков."""
    raw = []

    def add(start, end, state):
        if end > start:
            raw.append(Segment(start, end, state))

    if not samples:
        add(since, until, UNKNOWN)
        return _merge(raw)

    cursor = since
    gap = datetime.timedelta(minutes=GAP_MINUTES)

    for i, sample in enumerate(samples):
        s_start = sample.time
        s_end = samples[i + 1].time if i + 1 < len(samples) else until
        s_end = min(s_end, until)

        # Запись подтверждает состояние лишь на ближайшие GAP_MINUTES;
        # дальше — только если пришла следующая запись.
        confirmed_until = s_start + gap
        known_end = min(s_end, confirmed_until)

        start = max(s_start, cursor)
        if start > cursor:
            add(cursor, start, UNKNOWN)

        add(start, max(start, min(known_end, until)), sample.state)

        if known_end < s_end:
            add(max(known_end, since), min(s_end, until), UNKNOWN)

        cursor = max(cursor, min(s_end, until))

    if cursor < until:
        add(cursor, until, UNKNOWN)

    return _merge(raw)


def _merge(segments):
    merged = []
    for seg in segments:
        if merged:
            last = merged[-1]
            if last.state == seg.state and last.end >= seg.start:
                if seg.end > last.end:
                    last.end = seg.end
                continue
        merged.append(seg)
    return merged


def summarize(segments):
    """Итоги по ленте: сколько было связи, сколько её не было, обрывы."""
    up = datetime.timedelta()
    down = datetime.timedelta()
    idle = datetime.timedelta()
    outages = []

    for seg in segments:
        if seg.state == UP:
            up += seg.duration
        elif seg.state == DOWN:
            down += seg.duration
            outages.append(seg)
        else:
            idle += seg.duration

    observed = up + down
    availability = (
        up.total_seconds() / observed.total_seconds() * 100.0
        if observed.total_seconds() > 0
        else None
    )
    longest = max((o.duration for o in outages), default=datetime.timedelta())

    return {
        "up": up,
        "down": down,
        "idle": idle,
        "observed": observed,
        "availability": availability,
        "outages": outages,
        "longest": longest,
    }


def format_duration(delta):
    total = int(delta.total_seconds())
    if total < 1:
        return "—"
    if total < 60:
        return "%d сек" % total
    if total < 3600:
        return "%d мин" % (total // 60)
    if total < 86400:
        return "%d ч %d мин" % (total // 3600, (total % 3600) // 60)
    return "%d д %d ч %d мин" % (
        total // 86400,
        (total % 86400) // 3600,
        (total % 3600) // 60,
    )
