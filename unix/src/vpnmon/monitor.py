"""Логика наблюдения, общая для трея и фонового режима.

Здесь нет ничего от GTK: один и тот же Monitor работает и под значком в
трее, и в systemd-сервисе на машине без графики.
"""

import datetime

from . import history, notify, sound, vpn


class Monitor(object):
    def __init__(self, config):
        self.config = config
        self.was_down = False
        self.last_alert = None
        self.paused_until = None
        self.state = history.UNKNOWN
        self.detail = "Проверка…"

        # Вызывается после каждой проверки: on_state(state, detail).
        self.on_state = None

    # --- пауза -----------------------------------------------------------

    def pause(self, minutes=60):
        self.paused_until = datetime.datetime.now() + datetime.timedelta(minutes=minutes)

    def resume(self):
        self.paused_until = None

    @property
    def paused(self):
        return self.paused_until is not None and self.paused_until > datetime.datetime.now()

    # --- проверка --------------------------------------------------------

    def tick(self, manual=False):
        now = datetime.datetime.now()

        if self.paused:
            return self._settle(
                history.UNKNOWN, "Пауза до %s" % self.paused_until.strftime("%H:%M"), now
            )

        self.paused_until = None

        if not self.config.enabled:
            return self._settle(history.UNKNOWN, "Наблюдение выключено", now)

        if not self.config.vpn_target:
            return self._settle(history.UNKNOWN, "VPN-подключение не выбрано", now)

        if not self.config.is_within_schedule(now) and not manual:
            self.was_down = False
            return self._settle(history.UNKNOWN, "Вне рабочего времени", now)

        name = vpn.describe(self.config.vpn_target)
        up = vpn.is_connected(self.config.vpn_target)

        if up:
            restored = self.was_down
            self.was_down = False
            self.last_alert = None

            if restored and self.config.notify_on_restore:
                if self.config.sound_enabled:
                    sound.play_restore()
                notify.show("VPN %s снова подключён" % name, "Связь восстановлена.")

            return self._settle(history.UP, "%s: подключён" % name, now)

        suppressed = (
            self.last_alert is not None
            and self.config.repeat_suppress_minutes > 0
            and (now - self.last_alert).total_seconds()
            < self.config.repeat_suppress_minutes * 60
        )

        if not suppressed:
            if self.config.sound_enabled:
                sound.play_alarm()
            notify.show(
                "VPN %s не подключён!" % name,
                "Проверьте подключение — оно отвалилось.",
                critical=True,
            )
            self.last_alert = now

        self.was_down = True
        return self._settle(history.DOWN, "%s: НЕ подключён" % name, now)

    def _settle(self, state, detail, now):
        history.record(now, state)
        self.state = state
        self.detail = detail
        if self.on_state:
            self.on_state(state, detail)
        return state

    def shutdown(self):
        """Отметить конец наблюдения.

        Без этой записи последнее известное состояние тянулось бы на графике
        до следующего запуска.
        """
        history.record(datetime.datetime.now(), history.UNKNOWN)
