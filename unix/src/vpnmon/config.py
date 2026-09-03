"""Настройки приложения.

Формат файла намеренно тот же, что у Windows-версии — простой key=value
в ~/.config/vpn-connect-monitoring/config.ini. Это позволяет держать одну
документацию на обе платформы и готовить конфиг заранее для раздачи команде.
"""

import os

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "vpn-connect-monitoring",
)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.ini")

_TRUE = ("1", "true", "yes", "да", "on")
_FALSE = ("0", "false", "no", "нет", "off")


class Config:
    def __init__(self):
        self.vpn_target = ""          # см. vpn.py: "iface:wg0" или "nm:office-vpn"
        self.enabled = True
        self.interval_seconds = 60
        self.work_start_minutes = 9 * 60
        self.work_end_minutes = 18 * 60
        self.days = [True, True, True, True, True, False, False]  # Пн..Вс
        self.repeat_suppress_minutes = 15
        self.notify_on_restore = True
        self.sound_enabled = True

    # --- расписание ------------------------------------------------------

    def day_enabled(self, weekday):
        """weekday в формате datetime.weekday(): понедельник = 0."""
        return self.days[weekday]

    def is_within_schedule(self, now):
        """Окно может пересекать полночь (например 22:00–06:00).

        В этом случае ночная половина относится к дню, когда окно началось,
        иначе переход с воскресенья на понедельник считался бы неверно.
        """
        now_min = now.hour * 60 + now.minute

        if self.work_end_minutes > self.work_start_minutes:
            return (
                self.day_enabled(now.weekday())
                and self.work_start_minutes <= now_min < self.work_end_minutes
            )

        if now_min >= self.work_start_minutes:
            return self.day_enabled(now.weekday())
        if now_min < self.work_end_minutes:
            return self.day_enabled((now.weekday() - 1) % 7)
        return False

    # --- чтение и запись -------------------------------------------------

    @staticmethod
    def _parse_bool(value, fallback):
        v = value.strip().lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
        return fallback

    @staticmethod
    def _parse_int(value, fallback, low, high):
        try:
            n = int(value.strip())
        except (TypeError, ValueError):
            return fallback
        return max(low, min(high, n))

    @classmethod
    def load(cls):
        cfg = cls()
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            # Отсутствующий или недоступный конфиг не должен мешать запуску.
            return cfg

        for raw in lines:
            line = raw.strip()
            if not line or line[0] in "#;":
                continue
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip().lower()
            value = value.strip()

            if key == "vpntarget":
                cfg.vpn_target = value
            elif key == "enabled":
                cfg.enabled = cls._parse_bool(value, cfg.enabled)
            elif key == "intervalseconds":
                cfg.interval_seconds = cls._parse_int(value, cfg.interval_seconds, 10, 3600)
            elif key == "workstartminutes":
                cfg.work_start_minutes = cls._parse_int(value, cfg.work_start_minutes, 0, 1439)
            elif key == "workendminutes":
                cfg.work_end_minutes = cls._parse_int(value, cfg.work_end_minutes, 0, 1439)
            elif key == "repeatsuppressminutes":
                cfg.repeat_suppress_minutes = cls._parse_int(
                    value, cfg.repeat_suppress_minutes, 0, 240
                )
            elif key == "notifyonrestore":
                cfg.notify_on_restore = cls._parse_bool(value, cfg.notify_on_restore)
            elif key == "soundenabled":
                cfg.sound_enabled = cls._parse_bool(value, cfg.sound_enabled)
            elif key == "days":
                parts = value.split(",")
                if len(parts) == 7:
                    cfg.days = [
                        cls._parse_bool(p, cfg.days[i]) for i, p in enumerate(parts)
                    ]

        return cfg

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        days = ",".join("1" if d else "0" for d in self.days)

        text = (
            "# VPN Connect Monitoring — настройки\n"
            "# Изменения проще делать через окно настроек приложения.\n"
            "\n"
            "VpnTarget=%s\n"
            "Enabled=%s\n"
            "IntervalSeconds=%d\n"
            "WorkStartMinutes=%d\n"
            "WorkEndMinutes=%d\n"
            "RepeatSuppressMinutes=%d\n"
            "NotifyOnRestore=%s\n"
            "SoundEnabled=%s\n"
            "Days=%s\n"
        ) % (
            self.vpn_target,
            "1" if self.enabled else "0",
            self.interval_seconds,
            self.work_start_minutes,
            self.work_end_minutes,
            self.repeat_suppress_minutes,
            "1" if self.notify_on_restore else "0",
            "1" if self.sound_enabled else "0",
            days,
        )

        # Пишем через временный файл: обрыв записи не должен оставить
        # половину конфига.
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, CONFIG_PATH)

    def clone(self):
        other = Config()
        other.__dict__.update(self.__dict__)
        other.days = list(self.days)
        return other
