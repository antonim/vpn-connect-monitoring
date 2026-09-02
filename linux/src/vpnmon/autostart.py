"""Автозапуск при входе в сессию.

Используется каталог автозапуска XDG (~/.config/autostart) — он понятен
GNOME, KDE, XFCE и всему остальному, что встречается на Ubuntu, и не
требует ни прав root, ни systemd. Для чисто серверного сценария есть
--daemon и обычный systemd user unit, но для настольной машины это лишнее.
"""

import os
import shutil
import sys

from . import APP_ID, APP_TITLE

AUTOSTART_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "autostart",
)
DESKTOP_PATH = os.path.join(AUTOSTART_DIR, APP_ID + ".desktop")


def _executable():
    """Команда запуска.

    После установки пакета это /usr/bin/vpn-connect-monitoring. При запуске
    из исходников подставляем текущий интерпретатор и путь к модулю, чтобы
    автозапуск работал и до сборки deb.
    """
    installed = shutil.which(APP_ID)
    if installed:
        return "%s --tray" % installed

    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return "env PYTHONPATH=%s %s -m vpnmon --tray" % (package_root, sys.executable)


def enabled():
    return os.path.exists(DESKTOP_PATH)


def enable():
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=%s\n"
        "Comment=Контроль подключения VPN в рабочее время\n"
        "Exec=%s\n"
        "Icon=network-vpn\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    ) % (APP_TITLE, _executable())

    tmp = DESKTOP_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, DESKTOP_PATH)


def disable():
    try:
        os.remove(DESKTOP_PATH)
    except OSError:
        pass


def set_enabled(value):
    if value:
        enable()
    else:
        disable()
