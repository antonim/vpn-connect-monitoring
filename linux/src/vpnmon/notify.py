"""Уведомления рабочего стола.

На Linux с этим ощутимо проще, чем на Windows: спецификации Desktop
Notifications достаточно, регистрировать идентификатор приложения и класть
ярлык в меню не требуется.

Важная деталь — уровень срочности. С ``-u critical`` GNOME держит баннер на
экране, пока его не закроют, а не прячет через несколько секунд. Именно
исчезающий баннер был причиной пропущенных обрывов в Windows-версии.
"""

import shutil
import subprocess

APP_NAME = "VPN Connect Monitoring"
ICON_ALARM = "network-vpn-disconnected-symbolic"
ICON_OK = "network-vpn-symbolic"

_notify_send = None
_checked = False


def _exe():
    global _notify_send, _checked
    if not _checked:
        _notify_send = shutil.which("notify-send")
        _checked = True
    return _notify_send


def available():
    return _exe() is not None


def show(title, text, critical=False):
    """Показать уведомление. Возвращает False, если показать нечем."""
    exe = _exe()
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

    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False
