"""Уведомления рабочего стола.

Linux: `notify-send` по спецификации Desktop Notifications. Уровень
срочности `critical` заставляет GNOME держать баннер, пока его не закроют,
а не прятать через несколько секунд — исчезающий баннер был причиной
пропущенных обрывов в Windows-версии.

macOS: сначала пробуем показать уведомление сами, через AppKit
(см. objc_bridge). Это единственный способ, при котором сообщение
приходит от имени нашей программы, с её значком и собственной строкой
в «Системных настройках».

Запасные пути — `terminal-notifier`, если он вдруг установлен, и
`osascript`. У `osascript` есть особенность, из-за которой он оказался
последним: уведомление приходит от имени «Script Editor», а если
уведомления этому приложению не разрешены — не приходит вовсе, причём
сам вызов при этом завершается успешно. Молчаливый отказ хуже явного,
поэтому полагаться на него как на основной путь нельзя.
"""

import os
import shutil
import subprocess
import sys

from . import bundle_path

APP_NAME = "VPN Connect Monitoring"
ICON_ALARM = "network-vpn-disconnected-symbolic"
ICON_OK = "network-vpn-symbolic"

# Идентификатор пакета .app. Тот же, что в Info.plist и в имени
# LaunchAgent: центр уведомлений по нему находит имя и значок.
BUNDLE_ID = "io.github.antonim.vpn-connect-monitoring"

IS_MACOS = sys.platform == "darwin"

_cache = {}


def _which(name):
    if name not in _cache:
        _cache[name] = shutil.which(name)
    return _cache[name]


def available():
    if IS_MACOS:
        return (
            _native_center() is not None
            or _which("terminal-notifier") is not None
            or _which("osascript") is not None
        )
    return _which("notify-send") is not None


def _spawn(args):
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def _show_linux(title, text, critical):
    exe = _which("notify-send")
    if not exe:
        return False

    args = [
        exe,
        "--app-name", APP_NAME,
        "--icon", ICON_ALARM if critical else ICON_OK,
        "--urgency", "critical" if critical else "normal",
    ]
    if not critical:
        # Обычные уведомления гасим сами; критические должен закрыть человек.
        args += ["--expire-time", "10000"]
    args += [title, text]
    return _spawn(args)


def _applescript_quote(value):
    """Экранирование для строкового литерала AppleScript."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


_native = {}


LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks"
              "/LaunchServices.framework/Support/lsregister")


def _register_bundle():
    """Обновить запись о пакете в LaunchServices.

    Центр уведомлений находит имя и значок отправителя через эту запись.
    Если она указывает на прежнее расположение пакета — а так бывает
    после обновления версии или переноса программы, — уведомления
    перестают приходить, причём молча: отправка по-прежнему возвращает
    успех. Регистрация идемпотентна и делается один раз за запуск.
    """
    bundle = bundle_path()
    if not bundle or not os.path.exists(LSREGISTER):
        return

    try:
        subprocess.run([LSREGISTER, "-f", bundle],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass


def _native_center():
    """Центр уведомлений AppKit или None, если путь недоступен.

    Результат запоминается: подмена идентификатора делается один раз
    за процесс, да и повторно загружать AppKit незачем.
    """
    if "center" in _native:
        return _native["center"]

    _native["center"] = None
    try:
        from . import objc_bridge

        _register_bundle()
        objc_bridge.set_bundle_identifier(BUNDLE_ID)
        center = objc_bridge.msg(
            objc_bridge.cls("NSUserNotificationCenter"), "defaultUserNotificationCenter"
        )
        if center:
            _native["bridge"] = objc_bridge
            _native["center"] = center
    except Exception:  # noqa: BLE001 — уведомления не должны ронять наблюдение
        pass

    return _native["center"]


def _show_macos_native(title, text):
    center = _native_center()
    if not center:
        return False

    objc_bridge = _native["bridge"]
    try:
        note = objc_bridge.msg(
            objc_bridge.msg(objc_bridge.cls("NSUserNotification"), "alloc"), "init"
        )
        objc_bridge.msg(note, "setTitle:", objc_bridge.nsstring(title),
                        argtypes=[objc_bridge.ID])
        objc_bridge.msg(note, "setInformativeText:", objc_bridge.nsstring(text),
                        argtypes=[objc_bridge.ID])
        objc_bridge.msg(center, "deliverNotification:", note,
                        argtypes=[objc_bridge.ID])
        return True
    except Exception:  # noqa: BLE001 — см. выше
        return False


def _show_macos(title, text, critical):
    if _show_macos_native(title, text):
        return True

    exe = _which("terminal-notifier")
    if exe:
        args = [
            exe,
            "-title", APP_NAME,
            "-subtitle", title,
            "-message", text,
            "-group", "vpn-connect-monitoring",  # новое уведомление заменяет старое
        ]
        if _spawn(args):
            return True

    exe = _which("osascript")
    if not exe:
        return False

    script = 'display notification "%s" with title "%s" subtitle "%s"' % (
        _applescript_quote(text),
        _applescript_quote(APP_NAME),
        _applescript_quote(title),
    )
    return _spawn([exe, "-e", script])


def backend():
    """Каким путём уйдут уведомления. Нужно диагностике.

    Различать пути важно: успешный вызов и показанное уведомление —
    не одно и то же, и по одному лишь True из show() понять, увидит ли
    человек предупреждение, нельзя.
    """
    if IS_MACOS:
        if _native_center() is not None:
            return "AppKit — от имени программы, со своим значком"
        if _which("terminal-notifier"):
            return "terminal-notifier — от своего имени"
        if _which("osascript"):
            return "osascript — от имени «Script Editor», может молча не показать"
        return "нет"
    return "notify-send" if _which("notify-send") else "нет"


def show(title, text, critical=False):
    """Показать уведомление. Возвращает False, если показать нечем."""
    if IS_MACOS:
        return _show_macos(title, text, critical)
    return _show_linux(title, text, critical)
