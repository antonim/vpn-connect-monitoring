"""Отчёт по журналу: лента состояний, итоги и таблица обрывов.

Отчёт — самостоятельный HTML со встроенным SVG, без внешних файлов и
библиотек. Такой формат выбран вместо рисования в GTK по двум причинам:
его можно переслать администратору как есть, и он не зависит от наличия
графического окружения — на сервере отчёт строится и просматривается
где угодно.

В один файл кладутся сразу все диапазоны, переключение между ними —
на месте, без обращения к приложению.
"""

import datetime
import html
import os

from . import history

RANGES = [(24, "24 часа"), (72, "3 дня"), (168, "7 дней"), (720, "30 дней")]

COLORS = {
    history.UP: "#2ea043",
    history.DOWN: "#da3633",
    history.UNKNOWN: "#d2d6dc",
}

STATE_NAMES = {
    history.UP: "подключено",
    history.DOWN: "нет связи",
    history.UNKNOWN: "не наблюдалось",
}

BAND_WIDTH = 1000
BAND_HEIGHT = 54


def _axis_step_hours(span_hours):
    for step in (1, 2, 3, 6, 12, 24, 48, 72, 120, 168):
        if span_hours / step <= 10:
            return step
    return 168


def _timeline_svg(segments, since, until):
    total = max(1.0, (until - since).total_seconds())

    def x_of(when):
        frac = (when - since).total_seconds() / total
        return max(0.0, min(1.0, frac)) * BAND_WIDTH

    parts = ['<svg viewBox="0 0 %d %d" class="band" preserveAspectRatio="none">'
             % (BAND_WIDTH, BAND_HEIGHT)]

    for seg in segments:
        x1 = x_of(seg.start)
        width = x_of(seg.end) - x1

        # Короткий обрыв на месячном диапазоне занимает доли пикселя. Такие
        # случаи важнее всего, поэтому им даётся видимый минимум — иначе
        # минутный обрыв просто исчезнет с графика.
        if seg.state == history.DOWN:
            width = max(width, BAND_WIDTH / 400.0)
        width = max(width, 0.5)

        title = "%s — %s\n%s (%s)" % (
            seg.start.strftime("%d.%m %H:%M"),
            seg.end.strftime("%d.%m %H:%M"),
            STATE_NAMES[seg.state],
            history.format_duration(seg.duration),
        )
        parts.append(
            '<rect x="%.3f" y="0" width="%.3f" height="%d" fill="%s"><title>%s</title></rect>'
            % (x1, width, BAND_HEIGHT, COLORS[seg.state], html.escape(title))
        )

    parts.append("</svg>")

    # Ось времени отдельным слоем: она не должна растягиваться вместе
    # с лентой, иначе подписи поедут.
    span_hours = (until - since).total_seconds() / 3600.0
    step = _axis_step_hours(span_hours)
    day_labels = step >= 24

    tick = since.replace(minute=0, second=0, microsecond=0)
    while tick.hour % step != 0 or tick < since:
        tick += datetime.timedelta(hours=1)

    ticks = []
    while tick <= until:
        pos = (tick - since).total_seconds() / total * 100.0
        label = tick.strftime("%d.%m") if day_labels else tick.strftime("%H:%M")
        ticks.append('<span class="tick" style="left:%.3f%%">%s</span>' % (pos, label))
        tick += datetime.timedelta(hours=step)

    return "".join(parts), "".join(ticks)


def _range_block(index, hours, label, now):
    since = now - datetime.timedelta(hours=hours)
    segments = history.build_segments(history.load(since), since, now)
    summary = history.summarize(segments)
    band, ticks = _timeline_svg(segments, since, now)

    availability = (
        "%.1f %%" % summary["availability"]
        if summary["availability"] is not None
        else "нет данных"
    )

    rows = []
    for seg in reversed(summary["outages"]):
        ongoing = seg is summary["outages"][-1] and (now - seg.end).total_seconds() < 1
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                seg.start.strftime("%d.%m.%Y %H:%M:%S"),
                "продолжается" if ongoing else seg.end.strftime("%d.%m.%Y %H:%M:%S"),
                history.format_duration(seg.duration),
                "связи нет прямо сейчас" if ongoing else "",
            )
        )

    if not rows:
        rows.append('<tr><td colspan="4" class="empty">За период обрывов не было.</td></tr>')

    return """
<section class="range" id="range-%d" %s>
  <div class="chart">
    %s
    <div class="axis">%s</div>
  </div>
  <p class="stats">
    <b>Доступность:</b> %s &nbsp;&nbsp;
    <b>Обрывов:</b> %d &nbsp;&nbsp;
    <b>Суммарно без связи:</b> %s &nbsp;&nbsp;
    <b>Самый долгий:</b> %s
  </p>
  <p class="stats muted">
    Под наблюдением: %s &nbsp;&nbsp; Не наблюдалось: %s
    (программа не работала, пауза, вне расписания)
  </p>
  <table>
    <thead><tr><th>Начало</th><th>Окончание</th><th>Длительность</th><th>Примечание</th></tr></thead>
    <tbody>%s</tbody>
  </table>
</section>""" % (
        index,
        "" if index == 0 else "hidden",
        band,
        ticks,
        availability,
        len(summary["outages"]),
        history.format_duration(summary["down"]),
        history.format_duration(summary["longest"]),
        history.format_duration(summary["observed"]),
        history.format_duration(summary["idle"]),
        "".join(rows),
    )


CSS = """
:root { color-scheme: light dark; }
body { font: 14px/1.5 system-ui, "Segoe UI", Ubuntu, sans-serif; margin: 0; padding: 24px;
       background: #fbfbfd; color: #1c1e21; }
h1 { font-size: 20px; margin: 0 0 4px; }
.generated { color: #6b7280; margin: 0 0 20px; font-size: 13px; }
.tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.tabs button { font: inherit; padding: 6px 14px; border: 1px solid #d0d5dd; border-radius: 6px;
               background: #fff; cursor: pointer; }
.tabs button[aria-selected="true"] { background: #1c1e21; color: #fff; border-color: #1c1e21; }
.chart { margin-bottom: 6px; }
.band { width: 100%; height: 54px; display: block; border: 1px solid #9aa0a6; border-radius: 3px; }
.axis { position: relative; height: 20px; margin-top: 4px; }
.tick { position: absolute; transform: translateX(-50%); font-size: 11px; color: #6b7280;
        white-space: nowrap; }
.legend { display: flex; gap: 18px; align-items: center; margin: 14px 0; flex-wrap: wrap; }
.legend span { display: flex; gap: 6px; align-items: center; }
.swatch { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }
.stats { margin: 6px 0; }
.muted { color: #6b7280; }
table { border-collapse: collapse; width: 100%; margin-top: 14px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #e5e7eb; }
th { background: #f3f4f6; font-weight: 600; }
td { color: #b42318; }
td.empty { color: #6b7280; text-align: center; }
@media (prefers-color-scheme: dark) {
  body { background: #16181c; color: #e6e8eb; }
  .tabs button { background: #24272c; color: #e6e8eb; border-color: #3a3f46; }
  .tabs button[aria-selected="true"] { background: #e6e8eb; color: #16181c; }
  th { background: #24272c; }
  th, td { border-color: #2c3036; }
  td { color: #ff7b72; }
}
"""

JS = """
document.querySelectorAll('.tabs button').forEach(function (btn) {
  btn.addEventListener('click', function () {
    document.querySelectorAll('.tabs button').forEach(function (b) {
      b.setAttribute('aria-selected', String(b === btn));
    });
    document.querySelectorAll('.range').forEach(function (sec) {
      sec.hidden = sec.id !== 'range-' + btn.dataset.index;
    });
  });
});
"""


def build_html(now=None):
    now = now or datetime.datetime.now()

    tabs = "".join(
        '<button data-index="%d" aria-selected="%s">%s</button>'
        % (i, "true" if i == 0 else "false", label)
        for i, (_, label) in enumerate(RANGES)
    )

    blocks = "".join(
        _range_block(i, hours, label, now) for i, (hours, label) in enumerate(RANGES)
    )

    legend = "".join(
        '<span><i class="swatch" style="background:%s"></i>%s</span>'
        % (COLORS[state], STATE_NAMES[state])
        for state in (history.UP, history.DOWN, history.UNKNOWN)
    )

    return """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>VPN Connect Monitoring — журнал подключения</title>
<style>%s</style></head><body>
<h1>Журнал подключения VPN</h1>
<p class="generated">Отчёт построен %s. Источник: %s</p>
<div class="tabs">%s</div>
<div class="legend">%s</div>
%s
<script>%s</script>
</body></html>""" % (
        CSS,
        now.strftime("%d.%m.%Y %H:%M:%S"),
        html.escape(history.HISTORY_PATH),
        tabs,
        legend,
        blocks,
        JS,
    )


def write(path=None, now=None):
    """Строит отчёт и возвращает путь к файлу."""
    if path is None:
        path = os.path.join(history.config.CONFIG_DIR, "report.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_html(now))
    return path
