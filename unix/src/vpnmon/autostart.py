"""Автозапуск при входе в сессию.

Linux: каталог автозапуска XDG (~/.config/autostart) — его понимают GNOME,
KDE, XFCE и всё остальное, что встречается на Ubuntu, и он не требует ни
прав root, ни systemd.

macOS: LaunchAgent в ~/Library/LaunchAgents. Файл создаётся с
``RunAtLoad``, но не с ``KeepAlive``: перезапускать приложение, которое
пользователь сам закрыл через меню, было бы навязчиво.
"""

import os
import shutil
import subprocess
import sys
import xml.sax.saxutils

from . import APP_ID, APP_TITLE

IS_MACOS = sys.platform == "darwin"

LABEL = "io.github.antonim.vpn-connect-monitoring"

AUTOSTART_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "autostart",
)
DESKTOP_PATH = os.path.join(AUTOSTART_DIR, APP_ID + ".desktop")

LAUNCH_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")
PLIST_PATH = os.path.join(LAUNCH_AGENTS_DIR, LABEL + ".plist")


def _command_parts():
    """Пара (аргументы запуска, каталог для PYTHONPATH или None).

    После установки пакета это /usr/bin/vpn-connect-monitoring (Linux) или
    /usr/local/bin/vpn-connect-monitoring (macOS), и PYTHONPATH не нужен.
    При запуске из исходников подставляем текущий интерпретатор и путь
    к пакету, чтобы автозапуск работал и до сборки.
    """
    installed = shutil.which(APP_ID)
    if installed:
        return [installed, "--tray"], None

    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [sys.executable, "-m", "vpnmon", "--tray"], package_root


# --- Linux ---------------------------------------------------------------

def _enable_linux():
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    args, package_root = _command_parts()

    if package_root:
        exec_line = "env PYTHONPATH=%s %s" % (package_root, " ".join(args))
    else:
        exec_line = " ".join(args)

    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=%s\n"
        "Comment=Контроль подключения VPN в рабочее время\n"
        "Exec=%s\n"
        "Icon=network-vpn\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    ) % (APP_TITLE, exec_line)

    tmp = DESKTOP_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, DESKTOP_PATH)


def _disable_linux():
    try:
        os.remove(DESKTOP_PATH)
    except OSError:
        pass


# --- macOS ---------------------------------------------------------------

def _launchctl(args):
    try:
        subprocess.run(
            ["launchctl"] + args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _enable_macos():
    os.makedirs(LAUNCH_AGENTS_DIR, exist_ok=True)
    args, package_root = _command_parts()

    program_args = "".join(
        "        <string>%s</string>\n" % xml.sax.saxutils.escape(a) for a in args
    )

    env_block = ""
    if package_root:
        env_block = (
            "    <key>EnvironmentVariables</key>\n"
            "    <dict>\n"
            "        <key>PYTHONPATH</key>\n"
            "        <string>%s</string>\n"
            "    </dict>\n"
        ) % xml.sax.saxutils.escape(package_root)

    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        "    <string>%s</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        "%s"
        "    </array>\n"
        "%s"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>ProcessType</key>\n"
        "    <string>Interactive</string>\n"
        "</dict>\n"
        "</plist>\n"
    ) % (LABEL, program_args, env_block)

    tmp = PLIST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, PLIST_PATH)

    # Перезагружаем агент, чтобы правки подхватились без выхода из системы.
    _launchctl(["unload", PLIST_PATH])
    _launchctl(["load", "-w", PLIST_PATH])


def _disable_macos():
    _launchctl(["unload", "-w", PLIST_PATH])
    try:
        os.remove(PLIST_PATH)
    except OSError:
        pass


# --- общий интерфейс -----------------------------------------------------

def path():
    return PLIST_PATH if IS_MACOS else DESKTOP_PATH


def enabled():
    return os.path.exists(path())


def enable():
    _enable_macos() if IS_MACOS else _enable_linux()


def disable():
    _disable_macos() if IS_MACOS else _disable_linux()


def set_enabled(value):
    if value:
        enable()
    else:
        disable()
