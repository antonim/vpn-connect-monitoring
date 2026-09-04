"""Значок в строке меню macOS.

AppKit вызывается напрямую через ctypes (см. objc_bridge): PyObjC на
macOS взять негде, а тянуть ради значка виртуальное окружение — значит
требовать сеть при установке и ломаться при каждом обновлении питона.
Сторонних библиотек, как и в остальных сборках, нет ни одной.

Состояние показывается символом рядом с названием: у строки меню нет
цветовой заливки, как у значка в трее, а полагаться на один цвет там,
где его нет, нельзя.

Пункты меню различаются номером (tag), а не отдельным селектором на
каждый: объявление класса Objective-C — операция разовая и на весь
процесс, и один обработчик с разбором номера читается лучше, чем семь
почти одинаковых.
"""

import ctypes
import os
import subprocess
import time
import traceback

from . import autostart, history, notify, report, sound, vpn
from .config import CONFIG_PATH, Config
from .monitor import Monitor
from .objc_bridge import (
    BOOL,
    CGFloat,
    ID,
    NSInteger,
    SEL,
    cls,
    define_class,
    msg,
    new,
    nsstring,
    retain,
    sel,
)

# Символы состояния. Взяты из базового набора, который есть в любом
# системном шрифте: экзотические эмодзи в строке меню отображаются
# неровно и разъезжаются по ширине.
SYMBOLS = {
    history.UP: "✓",
    history.DOWN: "!",
    history.UNKNOWN: "–",
}

# Значения из AppKit; заголовочных файлов у нас нет, поэтому константы
# выписаны здесь с указанием, откуда они.
NS_VARIABLE_STATUS_ITEM_LENGTH = -1.0  # NSVariableStatusItemLength
NS_ACTIVATION_POLICY_ACCESSORY = 1     # NSApplicationActivationPolicyAccessory

# Номера пунктов меню.
TAG_REPORT = 1
TAG_SETTINGS = 2
TAG_CHECK_NOW = 3
TAG_PAUSE = 4
TAG_SOUND = 5
TAG_AUTOSTART = 6
TAG_QUIT = 7

# Приложение живёт в единственном экземпляре, а обработчики Objective-C
# получают только указатель на объект-приёмник и до питоновского
# состояния сами добраться не могут — поэтому ссылка лежит здесь.
_controller = None
_target_class = None


def _report_failure(where, exc):
    """Показать сбой обработчика.

    Исключение, вылетевшее в обработчик Objective-C, ctypes проглатывает:
    печатает «Exception ignored» в поток ошибок и продолжает работу. У
    программы, запущенной из автозапуска, этого потока никто не читает,
    поэтому сбой превратился бы в молча переставший работать пункт меню.
    """
    traceback.print_exc()
    notify.show("Сбой в %s" % where, "%s: %s" % (type(exc).__name__, exc))


def _dispatch(_self, _cmd, sender):
    if _controller is None:
        return
    try:
        _controller.on_menu(msg(sender, "tag", restype=NSInteger), sender)
    except Exception as exc:  # noqa: BLE001 — иначе сбой останется незамеченным
        _report_failure("меню", exc)


def _dispatch_tick(_self, _cmd, _timer):
    if _controller is None:
        return
    try:
        _controller.on_tick()
    except Exception as exc:  # noqa: BLE001 — см. _report_failure
        _report_failure("проверке", exc)


def _targets_comment():
    """Список найденных подключений — в шапку свежесозданного конфига.

    Без него человек, открывший файл настроек впервые, видит пустое
    VpnTarget и не может догадаться, что туда вписывать: имена служб
    выдаёт scutil, а имена интерфейсов — ifconfig.
    """
    try:
        targets = vpn.list_targets()
    except Exception:  # noqa: BLE001 — подсказка не должна мешать запуску
        return None

    if not targets:
        return ("VPN-подключений на этом компьютере не найдено.\n"
                "Поднимите VPN и нажмите «Проверить сейчас».")

    lines = ["Впишите в VpnTarget одно из найденных подключений:", ""]
    lines += ["  %-28s %s" % (t.key, t.label) for t in targets]
    return "\n".join(lines)


def _target():
    """Объект, на который ссылаются пункты меню и таймер.

    Класс объявляется один раз за процесс: повторный
    objc_allocateClassPair с тем же именем вернул бы NULL.
    """
    global _target_class

    if _target_class is None:
        _target_class = define_class("VpnmonMenuTarget", {
            "menuAction:": (_dispatch, "v@:@"),
            "onTimer:": (_dispatch_tick, "v@:@"),
        })
    return retain(msg(msg(_target_class, "alloc"), "init"))


class MenuBarApp(object):
    """Контроллер значка."""

    def __init__(self, open_settings=False):
        global _controller

        self.config = Config.load()
        self.monitor = Monitor(self.config)
        self.monitor.on_state = self._on_state
        self.paused_marked = False
        # Первая проверка выполняется сразу, дальше — по интервалу.
        self.next_check = 0.0

        history.prune()
        # Пакет надо зарегистрировать до первого уведомления, иначе оно
        # придёт от имени «Python»: центр уведомлений берёт имя
        # и значок у зарегистрированного приложения.
        notify.prepare()

        _controller = self
        self.target = _target()

        self.status_item = retain(
            msg(msg(cls("NSStatusBar"), "systemStatusBar"), "statusItemWithLength:",
                NS_VARIABLE_STATUS_ITEM_LENGTH, argtypes=[CGFloat])
        )
        self._set_status_title("VPN –")

        self._build_menu()
        # Первая проверка — сразу, не дожидаясь таймера: иначе значок
        # секунду показывал бы «неизвестно» вместо настоящего состояния.
        self.on_tick()

        # Первый запуск распознаём по отсутствию конфига: пакет .app
        # запускается двойным щелчком без аргументов, и человеку нужно
        # сразу показать, где выбирается подключение.
        if open_settings or not os.path.exists(CONFIG_PATH):
            self.open_settings()

    # --- меню ------------------------------------------------------------

    def _set_status_title(self, text):
        # У современного NSStatusItem заголовок ставится на кнопке;
        # setTitle: на самом элементе объявлен устаревшим ещё в 10.10.
        button = msg(self.status_item, "button")
        target = button if button else self.status_item
        msg(target, "setTitle:", nsstring(text), argtypes=[ID])

    def _build_menu(self):
        menu = retain(new("NSMenu"))
        # Пункты включаются нашим кодом, а не автоматикой AppKit:
        # у элемента строки меню нет активного окна, и по умолчанию
        # AppKit гасил бы всё меню целиком.
        msg(menu, "setAutoenablesItems:", False, argtypes=[BOOL])

        self.status_entry = self._add(menu, "Проверка…", None)
        msg(self.status_entry, "setEnabled:", False, argtypes=[BOOL])
        msg(menu, "addItem:", msg(cls("NSMenuItem"), "separatorItem"), argtypes=[ID])

        self._add(menu, "Журнал подключения…", TAG_REPORT)
        self._add(menu, "Настройки…", TAG_SETTINGS)
        self._add(menu, "Проверить сейчас", TAG_CHECK_NOW)

        self.pause_entry = self._add(menu, "Пауза на 1 час", TAG_PAUSE)
        self.sound_entry = self._add(menu, "Звуковой сигнал", TAG_SOUND)
        self._set_state(self.sound_entry, self.config.sound_enabled)

        # В GTK-версии это флажок в окне настроек; здесь окна настроек
        # нет, поэтому автозапуск переключается прямо из меню.
        self.autostart_entry = self._add(menu, "Запускать при входе в систему",
                                         TAG_AUTOSTART)
        self._set_state(self.autostart_entry, autostart.enabled())

        msg(menu, "addItem:", msg(cls("NSMenuItem"), "separatorItem"), argtypes=[ID])
        self._add(menu, "Выход", TAG_QUIT)

        self.menu = menu
        msg(self.status_item, "setMenu:", menu, argtypes=[ID])

    def _add(self, menu, title, tag):
        action = sel("menuAction:") if tag is not None else None
        item = msg(msg(cls("NSMenuItem"), "alloc"),
                   "initWithTitle:action:keyEquivalent:",
                   nsstring(title), action, nsstring(""),
                   argtypes=[ID, SEL, ID])
        if tag is not None:
            msg(item, "setTag:", tag, argtypes=[NSInteger])
            msg(item, "setTarget:", self.target, argtypes=[ID])
            msg(item, "setEnabled:", True, argtypes=[BOOL])
        msg(menu, "addItem:", item, argtypes=[ID])
        return item

    @staticmethod
    def _set_state(item, on):
        msg(item, "setState:", 1 if on else 0, argtypes=[NSInteger])

    @staticmethod
    def _state(item):
        return msg(item, "state", restype=NSInteger)

    # --- действия --------------------------------------------------------

    def on_menu(self, tag, sender):
        if tag == TAG_REPORT:
            self.open_report()
        elif tag == TAG_SETTINGS:
            self.open_settings()
        elif tag == TAG_CHECK_NOW:
            self.check_now()
        elif tag == TAG_PAUSE:
            self.toggle_pause(sender)
        elif tag == TAG_SOUND:
            self.toggle_sound(sender)
        elif tag == TAG_AUTOSTART:
            self.toggle_autostart(sender)
        elif tag == TAG_QUIT:
            self.quit()

    def open_report(self):
        path = report.write()
        try:
            subprocess.Popen(["open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            notify.show("Отчёт построен", path)

    def open_settings(self):
        """Настройки правятся в конфиге.

        Полноценное окно — заметный объём кода ради полутора десятков
        полей. Открываем сам файл в редакторе по умолчанию: формат
        простой и описан в README, а после сохранения настройки
        подхватываются пунктом «Проверить сейчас».
        """
        if not os.path.exists(CONFIG_PATH):
            try:
                self.config.save(extra_comment=_targets_comment())
            except OSError as exc:
                notify.show("Файл настроек", "Не удалось создать: %s" % exc)
                return
        try:
            subprocess.Popen(["open", "-t", CONFIG_PATH],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            notify.show("Файл настроек", CONFIG_PATH)

    def check_now(self):
        # Перечитываем конфиг: его могли поправить в редакторе.
        self.config = Config.load()
        self.monitor.config = self.config
        self.monitor.last_alert = None
        self._set_state(self.sound_entry, self.config.sound_enabled)
        self.next_check = time.monotonic() + max(1, self.config.interval_seconds)
        self.monitor.tick(manual=True)

    def toggle_pause(self, sender):
        if self._state(sender):
            self._set_state(sender, False)
            self.monitor.resume()
        else:
            self._set_state(sender, True)
            self.monitor.pause(60)
        self.monitor.tick()

    def toggle_sound(self, sender):
        enabled = not self._state(sender)
        self._set_state(sender, enabled)
        self.config.sound_enabled = enabled
        try:
            self.config.save()
        except OSError:
            pass
        if enabled:
            sound.play_restore()

    def toggle_autostart(self, sender):
        try:
            autostart.set_enabled(not self._state(sender))
        except OSError as exc:
            notify.show("Автозапуск", "Не удалось изменить: %s" % exc)
        self._set_state(sender, autostart.enabled())

    def quit(self):
        self.monitor.shutdown()
        msg(msg(cls("NSApplication"), "sharedApplication"), "terminate:", None,
            argtypes=[ID])

    # --- таймер ----------------------------------------------------------

    def on_tick(self):
        """Раз в секунду; проверка — когда истёк интервал из настроек.

        Секундный таймер вместо таймера на интервал опроса избавляет от
        перепланирования при изменении настроек: новый интервал
        подхватывается сам.
        """
        now = time.monotonic()
        if now < self.next_check:
            return
        self.next_check = now + max(1, self.config.interval_seconds)
        self.monitor.tick()

    def _on_state(self, state, detail):
        self._set_status_title("VPN %s" % SYMBOLS.get(state, SYMBOLS[history.UNKNOWN]))
        msg(self.status_entry, "setTitle:", nsstring(detail), argtypes=[ID])

        # Пауза могла истечь сама — снимаем отметку, чтобы меню не врало.
        if self._state(self.pause_entry) and not self.monitor.paused:
            self._set_state(self.pause_entry, False)


def run(open_settings=False):
    # Пул нужен всему, что создаётся до запуска цикла событий: без него
    # автоосвобождаемые объекты некому принять.
    pool = new("NSAutoreleasePool")

    app = msg(cls("NSApplication"), "sharedApplication")
    # Accessory: программа живёт в строке меню, без значка в Dock
    # и без пункта в переключателе приложений.
    msg(app, "setActivationPolicy:", NS_ACTIVATION_POLICY_ACCESSORY,
        argtypes=[NSInteger])

    controller = MenuBarApp(open_settings=open_settings)

    retain(msg(cls("NSTimer"),
               "scheduledTimerWithTimeInterval:target:selector:userInfo:repeats:",
               1.0, controller.target, sel("onTimer:"), None, True,
               argtypes=[ctypes.c_double, ID, SEL, ID, BOOL]))

    msg(pool, "drain")
    msg(app, "run")
