"""Обнаружение VPN-подключений и проверка их состояния.

Поддерживаются два источника, как они реально встречаются на Ubuntu:

* сетевые интерфейсы (`wg0`, `tun0`, `ppp0`) — WireGuard, OpenVPN, pptp;
* подключения NetworkManager — они существуют в конфигурации даже когда
  выключены, и это важно: список для выбора должен показывать все
  настроенные VPN, а не только поднятые сейчас.

Цель хранится в конфиге строкой с префиксом: ``iface:wg0`` или ``nm:office-vpn``.
Строка без префикса трактуется как имя интерфейса — так проще править
конфиг руками.
"""

import os
import subprocess

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
        self.kind = kind          # "iface" | "nm"
        self.name = name
        self.label = label

    @property
    def key(self):
        return "%s:%s" % (self.kind, self.name)


# --- интерфейсы ----------------------------------------------------------

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


def list_interfaces():
    """Интерфейсы, похожие на VPN. Возвращает список Target."""
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


def iface_is_up(name):
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


# --- NetworkManager ------------------------------------------------------

def _nmcli(args):
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-e", "no"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


def list_nm_connections():
    """Настроенные в NetworkManager VPN-подключения (включая выключенные)."""
    text = _nmcli(["-f", "NAME,TYPE", "connection", "show"])
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
    text = _nmcli(["-f", "NAME", "connection", "show", "--active"])
    if text is None:
        return False
    return name in [l.strip() for l in text.splitlines()]


# --- общий интерфейс -----------------------------------------------------

def list_targets():
    """Всё, что можно выбрать для наблюдения."""
    return list_interfaces() + list_nm_connections()


def parse_target(value):
    """Разбирает строку из конфига в пару (kind, name)."""
    value = (value or "").strip()
    if not value:
        return None, ""
    if value.startswith("iface:"):
        return "iface", value[6:]
    if value.startswith("nm:"):
        return "nm", value[3:]
    # Без префикса — считаем именем интерфейса.
    return "iface", value


def is_connected(target_value):
    kind, name = parse_target(target_value)
    if not name:
        return False
    if kind == "nm":
        return nm_is_active(name)
    return iface_is_up(name)


def describe(target_value):
    """Человекочитаемое имя цели для уведомлений и подсказок."""
    _, name = parse_target(target_value)
    return name or "?"
