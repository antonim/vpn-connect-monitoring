"""Уведомления рабочего стола.

Linux: `notify-send` по спецификации Desktop Notifications. Уровень
срочности `critical` заставляет GNOME держать баннер, пока его не закроют,
а не прятать через несколько секунд — исчезающий баннер был причиной
пропущенных обрывов в Windows-версии.

macOS: `terminal-notifier`, если он установлен, иначе `osascript`.
У `osascript` два известных ограничения, и оба стоит понимать:
уведомление приходит от имени «Script Editor», а не от нашей программы,
и его нельзя сделать несмахиваемым. `terminal-notifier` умеет и своё имя,
и щелчок по уведомлению, поэтому предпочитаем его.
"""

import shutil
import subprocess
import sys

APP_NAME = "VPN Connect Monitoring"
ICON_ALARM = "network-vpn-disconnected-symbolic"
ICON_OK = "network-vpn-symbolic"

IS_MACOS = sys.platform == "darwin"

_cache = {}


def _which(name):
    if name not in _cache:
        _cache[name] = shutil.which(name)
    return _cache[name]


def available():
    if IS_MACOS:
        return _which("terminal-notifier") is not None or _which("osascript") is not None
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


def _show_macos(title, text, critical):
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


def show(title, text, critical=False):
    """Показать уведомление. Возвращает False, если показать нечем."""
    if IS_MACOS:
        return _show_macos(title, text, critical)
    return _show_linux(title, text, critical)
