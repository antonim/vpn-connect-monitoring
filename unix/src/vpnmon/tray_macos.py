"""Значок в строке меню macOS (PyObjC, без сторонних библиотек).

PyObjC входит в состав системного /usr/bin/python3 (ставится вместе с
Command Line Tools), поэтому сторонних зависимостей вроде rumps не нужно.
Если PyObjC всё же недоступен, cli.py ловит ImportError и предлагает
режим --daemon.

Состояние показывается символом рядом с названием: у строки меню нет
цветовой заливки, как у значка в трее, а полагаться на один цвет там,
где его нет, нельзя.
"""

import os
import subprocess

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from . import history, notify, report, sound
from .config import Config
from .monitor import Monitor

# Символы состояния. Взяты из базового набора, который есть в любом
# системном шрифте: экзотические эмодзи в строке меню отображаются
# неровно и разъезжаются по ширине.
SYMBOLS = {
    history.UP: "✓",
    history.DOWN: "!",
    history.UNKNOWN: "–",
}


class MenuBarApp(NSObject):
    """Контроллер значка. NSObject нужен для целей действий меню."""

    def initWithSettings_(self, open_settings):
        # Идиома PyObjC: init базового класса возвращает объект, и
        # присвоить его обратно в self обязательно.
        self = objc.super(MenuBarApp, self).init()
        if self is None:
            return None

        self.config = Config.load()
        self.monitor = Monitor(self.config)
        self.monitor.on_state = self._on_state
        self.timer = None

        history.prune()

        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self.status_item.setTitle_("VPN –")

        self._build_menu()
        self._reschedule()
        self.monitor.tick()

        if open_settings:
            self.openSettings_(None)

        return self

    # --- меню ------------------------------------------------------------

    def _build_menu(self):
        menu = NSMenu.alloc().init()

        self.status_entry = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Проверка…", None, ""
        )
        self.status_entry.setEnabled_(False)
        menu.addItem_(self.status_entry)
        menu.addItem_(NSMenuItem.separatorItem())

        self._add(menu, "Журнал подключения…", "openReport:")
        self._add(menu, "Настройки…", "openSettings:")
        self._add(menu, "Проверить сейчас", "checkNow:")

        self.pause_entry = self._add(menu, "Пауза на 1 час", "togglePause:")
        self.sound_entry = self._add(menu, "Звуковой сигнал", "toggleSound:")
        self.sound_entry.setState_(1 if self.config.sound_enabled else 0)

        menu.addItem_(NSMenuItem.separatorItem())
        self._add(menu, "Выход", "quit:")

        self.status_item.setMenu_(menu)

    def _add(self, menu, title, selector):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
        item.setTarget_(self)
        menu.addItem_(item)
        return item

    # --- действия --------------------------------------------------------

    def openReport_(self, _sender):
        path = report.write()
        try:
            subprocess.Popen(["open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            notify.show("Отчёт построен", path)

    def openSettings_(self, _sender):
        """Настройки правятся в конфиге.

        Полноценное окно на PyObjC — заметный объём кода, который на этой
        машине проверить нечем. Пока открываем сам файл в редакторе по
        умолчанию: формат простой и описан в README, а после сохранения
        настройки подхватываются пунктом «Проверить сейчас».
        """
        from .config import CONFIG_PATH

        if not os.path.exists(CONFIG_PATH):
            self.config.save()
        try:
            subprocess.Popen(["open", "-t", CONFIG_PATH],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            notify.show("Файл настроек", CONFIG_PATH)

    def checkNow_(self, _sender):
        # Перечитываем конфиг: его могли поправить в редакторе.
        self.config = Config.load()
        self.monitor.config = self.config
        self.monitor.last_alert = None
        self.sound_entry.setState_(1 if self.config.sound_enabled else 0)
        self._reschedule()
        self.monitor.tick(manual=True)

    def togglePause_(self, sender):
        if sender.state():
            sender.setState_(0)
            self.monitor.resume()
        else:
            sender.setState_(1)
            self.monitor.pause(60)
        self.monitor.tick()

    def toggleSound_(self, sender):
        enabled = not sender.state()
        sender.setState_(1 if enabled else 0)
        self.config.sound_enabled = enabled
        try:
            self.config.save()
        except OSError:
            pass
        if enabled:
            sound.play_restore()

    def quit_(self, _sender):
        self.monitor.shutdown()
        NSApplication.sharedApplication().terminate_(None)

    # --- таймер ----------------------------------------------------------

    def _reschedule(self):
        if self.timer is not None:
            self.timer.invalidate()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            max(1, self.config.interval_seconds), self, "onTimer:", None, True
        )

    def onTimer_(self, _timer):
        self.monitor.tick()

    def _on_state(self, state, detail):
        self.status_item.setTitle_("VPN %s" % SYMBOLS.get(state, SYMBOLS[history.UNKNOWN]))
        self.status_entry.setTitle_(detail)

        # Пауза могла истечь сама — снимаем отметку, чтобы меню не врало.
        if self.pause_entry.state() and not self.monitor.paused:
            self.pause_entry.setState_(0)


def run(open_settings=False):
    app = NSApplication.sharedApplication()
    # Accessory: программа живёт в строке меню, без значка в Dock
    # и без пункта в переключателе приложений.
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = MenuBarApp.alloc().initWithSettings_(open_settings)
    if controller is None:
        raise RuntimeError("не удалось создать значок в строке меню")

    AppHelper.runEventLoop()
