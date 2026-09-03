"""Обнаружение VPN-подключений и проверка их состояния.

Источники различаются по системам, поэтому модуль разделён на две части.

Linux:

* сетевые интерфейсы (`wg0`, `tun0`, `ppp0`) — WireGuard, OpenVPN, pptp;
* подключения NetworkManager — они существуют в конфигурации даже когда
  выключены, и это важно: список для выбора должен показывать все
  настроенные VPN, а не только поднятые сейчас.

macOS:

* службы сетевых подключений (``scutil --nc``) — встроенные IKEv2, IPsec
  и L2TP из «Системных настроек»;
* интерфейсы ``utun`` — их поднимают WireGuard, OpenVPN и Tunnelblick.

Цель хранится в конфиге строкой с префиксом: ``iface:wg0``,
``nm:office-vpn`` (Linux) или ``nc:Office VPN`` (macOS). Строка без
префикса трактуется как имя интерфейса — так проще править конфиг руками.
"""

import os
import re
import subprocess
import sys

IS_MACOS = sys.platform == "darwin"

SYS_NET = "/sys/class/net"

# Флаги из linux/if.h
IFF_UP = 0x1
IFF_RUNNING = 0x40

# Имена, за которыми обычно скрывается VPN. Обычные ethernet/wifi-интерфейсы
# сюда не попадают, чтобы не засорять список выбора.
VPN_PREFIXES = ("wg", "tun", "tap", "ppp", "vpn", "nordlynx", "proton", "ipsec")


class Target(object):
    """Кандидат для наблюдения: что показать в списке и как проверять."""

    def __init__(self, kind, name, label):
        self.kind = kind          # "iface" | "nm" | "nc"
        self.name = name
        self.label = label

    @property
    def key(self):
        return "%s:%s" % (self.kind, self.name)


def _run(args, timeout=5):
    """Запускает команду и возвращает stdout или None."""
    try:
        out = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


# =========================== Linux ======================================

def _read(path):
    try:
        with open(path, "r") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _iface_kind(name):
    """Грубое определение типа интерфейса по sysfs."""
    if os.path.exists(os.path.join(SYS_NET, name, "tun_flags")):
        return "tun/tap"
    uevent = _read(os.path.join(SYS_NET, name, "uevent"))
    for line in uevent.splitlines():
        if line.startswith("DEVTYPE="):
            return line.split("=", 1)[1]
    return ""


def list_interfaces_linux():
    result = []
    try:
        names = sorted(os.listdir(SYS_NET))
    except OSError:
        return result

    for name in names:
        if name == "lo":
            continue

        kind = _iface_kind(name)
        looks_like_vpn = (
            name.startswith(VPN_PREFIXES)
            or kind in ("wireguard", "tun/tap")
        )
        if not looks_like_vpn:
            continue

        label = name if not kind else "%s (%s)" % (name, kind)
        result.append(Target("iface", name, label))

    return result


def iface_is_up_linux(name):
    """Поднят ли интерфейс.

    Проверяем флаги, а не только operstate: у tun- и wireguard-интерфейсов
    operstate сплошь и рядом равен "unknown" даже когда связь есть, и
    сравнение с "up" давало бы постоянную ложную тревогу.
    """
    base = os.path.join(SYS_NET, name)
    if not os.path.isdir(base):
        return False

    flags_raw = _read(os.path.join(base, "flags"))
    if not flags_raw:
        return False
    try:
        flags = int(flags_raw, 16)
    except ValueError:
        return False

    if not flags & IFF_UP:
        return False

    operstate = _read(os.path.join(base, "operstate"))
    if operstate == "down":
        return False

    # IFF_RUNNING выставлен не у всех драйверов, поэтому он лишь усиливает
    # решение, а не отменяет его.
    return bool(flags & IFF_RUNNING) or operstate in ("up", "unknown", "")


def list_nm_connections():
    """Настроенные в NetworkManager VPN-подключения (включая выключенные)."""
    text = _run(["nmcli", "-t", "-e", "no", "-f", "NAME,TYPE", "connection", "show"])
    if text is None:
        return []

    result = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, _, ctype = line.rpartition(":")
        if ctype in ("vpn", "wireguard", "tun"):
            result.append(Target("nm", name, "%s (NetworkManager, %s)" % (name, ctype)))
    return result


def nm_is_active(name):
    text = _run(["nmcli", "-t", "-e", "no", "-f", "NAME", "connection", "show", "--active"])
    if text is None:
        return False
    return name in [l.strip() for l in text.splitlines()]


# =========================== macOS ======================================

# Строка вывода `scutil --nc list` выглядит так:
#   * (Disconnected)  A1B2-... PPP (L2TP) "Office VPN" [PPP:L2TP]
# Имя службы всегда в кавычках, состояние — в первых скобках.
_NC_LINE = re.compile(r'\((?P<state>[A-Za-z]+)\)\s.*?"(?P<name>[^"]+)"')


def list_nc_services():
    """Службы сетевых подключений macOS, включая выключенные."""
    text = _run(["scutil", "--nc", "list"])
    if text is None:
        return []

    result = []
    for line in text.splitlines():
        match = _NC_LINE.search(line)
        if not match:
            continue
        name = match.group("name")
        result.append(Target("nc", name, "%s (сетевая служба)" % name))
    return result


def nc_is_connected(name):
    """Состояние службы по её имени.

    `scutil --nc status` печатает состояние первой строкой: Connected,
    Disconnected, Connecting и т. д. Промежуточные состояния считаем
    отсутствием связи — наблюдателю важен факт работающего туннеля.
    """
    text = _run(["scutil", "--nc", "status", name])
    if not text:
        return False
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    return first == "Connected"


def _ifconfig(name):
    return _run(["ifconfig", name]) or ""


def list_interfaces_macos():
    """Интерфейсы utun с назначенным адресом.

    Пустые utun отбрасываем намеренно: macOS держит несколько таких
    интерфейсов под свои службы (Private Relay, Handoff), и без фильтра
    список выбора состоял бы в основном из них.
    """
    text = _run(["ifconfig", "-l"])
    if text is None:
        return []

    result = []
    for name in text.split():
        if not name.startswith(("utun", "ppp", "ipsec", "tun", "tap")):
            continue
        info = _ifconfig(name)
        if "inet " not in info:
            continue
        result.append(Target("iface", name, "%s (интерфейс)" % name))
    return result


def iface_is_up_macos(name):
    info = _ifconfig(name)
    if not info:
        return False
    if "inet " not in info:
        return False
    flags = info.split("flags=", 1)[1].split(">", 1)[0] if "flags=" in info else ""
    return "UP" in flags and "RUNNING" in flags


# ======================= общий интерфейс ================================

def list_targets():
    """Всё, что можно выбрать для наблюдения."""
    if IS_MACOS:
        return list_nc_services() + list_interfaces_macos()
    return list_interfaces_linux() + list_nm_connections()


def parse_target(value):
    """Разбирает строку из конфига в пару (kind, name)."""
    value = (value or "").strip()
    if not value:
        return None, ""
    for prefix, kind in (("iface:", "iface"), ("nm:", "nm"), ("nc:", "nc")):
        if value.startswith(prefix):
            return kind, value[len(prefix):]
    # Без префикса — считаем именем интерфейса.
    return "iface", value


def is_connected(target_value):
    kind, name = parse_target(target_value)
    if not name:
        return False
    if kind == "nm":
        return nm_is_active(name)
    if kind == "nc":
        return nc_is_connected(name)
    return iface_is_up_macos(name) if IS_MACOS else iface_is_up_linux(name)


def describe(target_value):
    """Человекочитаемое имя цели для уведомлений и подсказок."""
    _, name = parse_target(target_value)
    return name or "?"
