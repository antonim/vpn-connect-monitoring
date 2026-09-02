"""Значок в трее и окно настроек (GTK 3 + AppIndicator).

На GNOME легаси-трей отсутствует, поэтому используется AppIndicator —
в Ubuntu расширение для него идёт из коробки. Библиотека называется
по-разному в зависимости от версии, поэтому пробуем оба имени.

Если индикатор недоступен вовсе (например, голый WM или сервер),
приложение не падает, а сообщает об этом и предлагает --daemon.
"""

import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import APP_ID, APP_TITLE, autostart, history, notify, report, sound, vpn  # noqa: E402
from .config import Config  # noqa: E402
from .monitor import Monitor  # noqa: E402

DAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

ICONS = {
    history.UP: "network-vpn-symbolic",
    history.DOWN: "network-error-symbolic",
    history.UNKNOWN: "network-offline-symbolic",
}


def _load_indicator():
    """Возвращает модуль AppIndicator или None."""
    for namespace in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(namespace, "0.1")
            return __import__("gi.repository." + namespace, fromlist=[namespace])
        except (ValueError, ImportError):
            continue
    return None


class TrayApp(object):
    def __init__(self, open_settings=False):
        self.config = Config.load()
        self.monitor = Monitor(self.config)
        self.monitor.on_state = self._on_state
        self.settings_window = None
        self.timeout_id = None

        history.prune()

        indicator_mod = _load_indicator()
        if indicator_mod is None:
            print(
                "Не найден AppIndicator — значок в трее показать нечем.\n"
                "Установите gir1.2-ayatanaappindicator3-0.1, либо запустите\n"
                "фоновый режим без значка:  %s --daemon" % APP_ID,
                file=sys.stderr,
            )
            raise SystemExit(2)

        self.indicator = indicator_mod.Indicator.new(
            APP_ID, ICONS[history.UNKNOWN],
            indicator_mod.IndicatorCategory.SYSTEM_SERVICES,
        )
        self.indicator.set_status(indicator_mod.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_TITLE)
        self._build_menu()

        self._reschedule()
        self.monitor.tick()

        if open_settings:
            self.show_settings()

    # --- меню -------------------------------------------------------------

    def _build_menu(self):
        menu = Gtk.Menu()

        self.mi_status = Gtk.MenuItem(label="Проверка…")
        self.mi_status.set_sensitive(False)
        menu.append(self.mi_status)
        menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.MenuItem(label="Журнал подключения…")
        item.connect("activate", lambda _w: self.open_report())
        menu.append(item)

        item = Gtk.MenuItem(label="Настройки…")
        item.connect("activate", lambda _w: self.show_settings())
        menu.append(item)

        item = Gtk.MenuItem(label="Проверить сейчас")
        item.connect("activate", lambda _w: self.monitor.tick(manual=True))
        menu.append(item)

        self.mi_pause = Gtk.CheckMenuItem(label="Пауза на 1 час")
        self.mi_pause.connect("toggled", self._on_pause_toggled)
        menu.append(self.mi_pause)

        self.mi_sound = Gtk.CheckMenuItem(label="Звуковой сигнал")
        self.mi_sound.set_active(self.config.sound_enabled)
        self.mi_sound.connect("toggled", self._on_sound_toggled)
        menu.append(self.mi_sound)

        menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.MenuItem(label="Выход")
        item.connect("activate", lambda _w: self.quit())
        menu.append(item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def _on_pause_toggled(self, widget):
        if widget.get_active():
            self.monitor.pause(60)
        else:
            self.monitor.resume()
        self.monitor.tick()

    def _on_sound_toggled(self, widget):
        # Переключатель в трее и флажок в настройках правят одно значение,
        # поэтому изменение сразу пишется на диск.
        self.config.sound_enabled = widget.get_active()
        self.config.save()
        if self.config.sound_enabled:
            sound.play_restore()

    # --- состояние --------------------------------------------------------

    def _on_state(self, state, detail):
        self.indicator.set_icon_full(ICONS.get(state, ICONS[history.UNKNOWN]), detail)
        self.mi_status.set_label(detail)

        # Пауза могла истечь сама — снимаем галочку, чтобы меню не врало.
        if self.mi_pause.get_active() and not self.monitor.paused:
            self.mi_pause.handler_block_by_func(self._on_pause_toggled)
            self.mi_pause.set_active(False)
            self.mi_pause.handler_unblock_by_func(self._on_pause_toggled)

    def _reschedule(self):
        if self.timeout_id is not None:
            GLib.source_remove(self.timeout_id)
        self.timeout_id = GLib.timeout_add_seconds(
            max(1, self.config.interval_seconds), self._on_timer
        )

    def _on_timer(self):
        self.monitor.tick()
        return True

    def apply_config(self, updated):
        self.config = updated
        self.monitor.config = updated
        # Новые настройки — новый повод предупредить.
        self.monitor.last_alert = None

        self.mi_sound.handler_block_by_func(self._on_sound_toggled)
        self.mi_sound.set_active(updated.sound_enabled)
        self.mi_sound.handler_unblock_by_func(self._on_sound_toggled)

        self._reschedule()
        self.monitor.tick()

    # --- действия ---------------------------------------------------------

    def open_report(self):
        path = report.write()
        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            notify.show("Отчёт построен", path)

    def show_settings(self):
        if self.settings_window is not None:
            self.settings_window.present()
            return
        self.settings_window = SettingsWindow(self)
        self.settings_window.connect(
            "destroy", lambda _w: setattr(self, "settings_window", None)
        )
        self.settings_window.show_all()

    def quit(self):
        self.monitor.shutdown()
        Gtk.main_quit()

    def run(self):
        Gtk.main()


class SettingsWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="%s — настройки" % APP_TITLE)
        self.app = app
        self.config = app.config.clone()

        self.set_default_size(520, -1)
        self.set_border_width(14)
        self.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.add(box)

        box.pack_start(self._connection_frame(), False, False, 0)
        box.pack_start(self._schedule_frame(), False, False, 0)
        box.pack_start(self._notify_frame(), False, False, 0)
        box.pack_start(self._buttons(), False, False, 0)

        self._load_values()

    # --- блоки ------------------------------------------------------------

    @staticmethod
    def _frame(title, child):
        frame = Gtk.Frame(label=" %s " % title)
        child.set_border_width(10)
        frame.add(child)
        return frame

    def _connection_frame(self):
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)

        grid.attach(Gtk.Label(label="VPN-подключение:", xalign=0), 0, 0, 1, 1)

        self.combo = Gtk.ComboBoxText.new_with_entry()
        self.targets = vpn.list_targets()
        for target in self.targets:
            self.combo.append_text(target.label)
        self.combo.set_hexpand(True)
        grid.attach(self.combo, 1, 0, 1, 1)

        refresh = Gtk.Button(label="Проверить")
        refresh.connect("clicked", lambda _w: self._refresh_status())
        grid.attach(refresh, 2, 0, 1, 1)

        self.status_label = Gtk.Label(xalign=0)
        grid.attach(self.status_label, 0, 1, 3, 1)

        return self._frame("Подключение", grid)

    def _schedule_frame(self):
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)

        grid.attach(Gtk.Label(label="Рабочие часы:", xalign=0), 0, 0, 1, 1)

        hours = Gtk.Box(spacing=6)
        self.start_h = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.start_m = Gtk.SpinButton.new_with_range(0, 59, 5)
        self.end_h = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.end_m = Gtk.SpinButton.new_with_range(0, 59, 5)
        for widget in (self.start_h, self.start_m, self.end_h, self.end_m):
            widget.set_width_chars(2)
        hours.pack_start(self.start_h, False, False, 0)
        hours.pack_start(Gtk.Label(label=":"), False, False, 0)
        hours.pack_start(self.start_m, False, False, 0)
        hours.pack_start(Gtk.Label(label="—"), False, False, 6)
        hours.pack_start(self.end_h, False, False, 0)
        hours.pack_start(Gtk.Label(label=":"), False, False, 0)
        hours.pack_start(self.end_m, False, False, 0)
        grid.attach(hours, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Дни недели:", xalign=0), 0, 1, 1, 1)
        days = Gtk.Box(spacing=4)
        self.day_checks = []
        for name in DAY_NAMES:
            check = Gtk.CheckButton(label=name)
            self.day_checks.append(check)
            days.pack_start(check, False, False, 0)
        grid.attach(days, 1, 1, 1, 1)

        return self._frame("Расписание", grid)

    def _notify_frame(self):
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)

        grid.attach(Gtk.Label(label="Интервал опроса:", xalign=0), 0, 0, 1, 1)
        self.interval = Gtk.SpinButton.new_with_range(10, 3600, 10)
        grid.attach(self.interval, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="секунд", xalign=0), 2, 0, 1, 1)

        grid.attach(Gtk.Label(label="Не повторять чаще:", xalign=0), 0, 1, 1, 1)
        self.repeat = Gtk.SpinButton.new_with_range(0, 240, 1)
        grid.attach(self.repeat, 1, 1, 1, 1)
        grid.attach(
            Gtk.Label(label="минут (0 — при каждой проверке)", xalign=0), 2, 1, 1, 1
        )

        self.chk_restore = Gtk.CheckButton(label="Уведомлять о восстановлении связи")
        grid.attach(self.chk_restore, 0, 2, 3, 1)

        self.chk_sound = Gtk.CheckButton(label="Звуковой сигнал при обрыве и восстановлении")
        grid.attach(self.chk_sound, 0, 3, 3, 1)

        self.chk_enabled = Gtk.CheckButton(label="Наблюдение включено")
        grid.attach(self.chk_enabled, 0, 4, 3, 1)

        self.chk_autostart = Gtk.CheckButton(label="Запускать при входе в систему")
        self.chk_autostart.connect("toggled", self._on_autostart_toggled)
        grid.attach(self.chk_autostart, 0, 5, 3, 1)

        return self._frame("Опрос и уведомления", grid)

    def _buttons(self):
        box = Gtk.Box(spacing=8)

        test = Gtk.Button(label="Тест уведомления")
        test.connect("clicked", lambda _w: self._test())
        box.pack_start(test, False, False, 0)

        journal = Gtk.Button(label="Журнал…")
        journal.connect("clicked", lambda _w: self.app.open_report())
        box.pack_start(journal, False, False, 0)

        save = Gtk.Button(label="Сохранить")
        save.get_style_context().add_class("suggested-action")
        save.connect("clicked", lambda _w: self._save())
        box.pack_end(save, False, False, 0)

        close = Gtk.Button(label="Закрыть")
        close.connect("clicked", lambda _w: self.destroy())
        box.pack_end(close, False, False, 0)

        return box

    # --- данные -----------------------------------------------------------

    def _load_values(self):
        entry = self.combo.get_child()
        current_kind, current_name = vpn.parse_target(self.config.vpn_target)
        for index, target in enumerate(self.targets):
            if target.kind == current_kind and target.name == current_name:
                self.combo.set_active(index)
                break
        else:
            entry.set_text(current_name)

        self.start_h.set_value(self.config.work_start_minutes // 60)
        self.start_m.set_value(self.config.work_start_minutes % 60)
        self.end_h.set_value(self.config.work_end_minutes // 60)
        self.end_m.set_value(self.config.work_end_minutes % 60)

        for check, value in zip(self.day_checks, self.config.days):
            check.set_active(value)

        self.interval.set_value(self.config.interval_seconds)
        self.repeat.set_value(self.config.repeat_suppress_minutes)
        self.chk_restore.set_active(self.config.notify_on_restore)
        self.chk_sound.set_active(self.config.sound_enabled)
        self.chk_enabled.set_active(self.config.enabled)

        self.chk_autostart.handler_block_by_func(self._on_autostart_toggled)
        self.chk_autostart.set_active(autostart.enabled())
        self.chk_autostart.handler_unblock_by_func(self._on_autostart_toggled)

        self._refresh_status()

    def _selected_target(self):
        index = self.combo.get_active()
        if 0 <= index < len(self.targets):
            return self.targets[index].key
        return self.combo.get_child().get_text().strip()

    def _refresh_status(self):
        target = self._selected_target()
        if not target:
            self.status_label.set_markup(
                '<span foreground="#b45309">Статус: подключение не выбрано</span>'
            )
            return
        if vpn.is_connected(target):
            self.status_label.set_markup('<span foreground="#2ea043">Статус: подключено</span>')
        else:
            self.status_label.set_markup('<span foreground="#da3633">Статус: не подключено</span>')

    def _on_autostart_toggled(self, widget):
        autostart.set_enabled(widget.get_active())

    def _test(self):
        if self.chk_sound.get_active():
            sound.play_alarm()
        notify.show(
            "Тест уведомления",
            "Так будет выглядеть и звучать предупреждение об обрыве VPN.",
            critical=True,
        )

    def _error(self, text):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK, text=text,
        )
        dialog.run()
        dialog.destroy()

    def _save(self):
        target = self._selected_target()
        if not target:
            self._error("Выберите VPN-подключение.")
            return
        if not any(check.get_active() for check in self.day_checks):
            self._error("Выберите хотя бы один день недели.")
            return

        self.config.vpn_target = target
        self.config.work_start_minutes = (
            int(self.start_h.get_value()) * 60 + int(self.start_m.get_value())
        )
        self.config.work_end_minutes = (
            int(self.end_h.get_value()) * 60 + int(self.end_m.get_value())
        )
        self.config.days = [check.get_active() for check in self.day_checks]
        self.config.interval_seconds = int(self.interval.get_value())
        self.config.repeat_suppress_minutes = int(self.repeat.get_value())
        self.config.notify_on_restore = self.chk_restore.get_active()
        self.config.sound_enabled = self.chk_sound.get_active()
        self.config.enabled = self.chk_enabled.get_active()

        try:
            self.config.save()
        except OSError as exc:
            self._error("Не удалось сохранить настройки:\n%s" % exc)
            return

        self.app.apply_config(self.config.clone())
        self.destroy()
