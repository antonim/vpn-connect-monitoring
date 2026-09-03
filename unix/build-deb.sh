#!/bin/bash
#
# Сборка пакета vpn-connect-monitoring_<версия>_all.deb.
#
# Пакет архитектурно-независимый: внутри только Python и текстовые файлы,
# компилировать нечего. Собирается штатным dpkg-deb, никаких инструментов
# сверх базовой Ubuntu не требуется.
#
# Использование:  ./build-deb.sh [каталог-вывода]

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
outdir="${1:-$here/build}"

package="vpn-connect-monitoring"
version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$here/src/vpnmon/__init__.py")"
if [ -z "$version" ]; then
    echo "Не удалось прочитать версию из src/vpnmon/__init__.py" >&2
    exit 1
fi

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT

echo "Сборка $package $version"

# --- раскладка файлов ----------------------------------------------------

install -d "$staging/DEBIAN"
install -d "$staging/usr/lib/$package/vpnmon"
install -d "$staging/usr/bin"
install -d "$staging/usr/share/applications"
install -d "$staging/usr/share/doc/$package"

install -m 644 "$here/src/vpnmon/"*.py "$staging/usr/lib/$package/vpnmon/"

cat > "$staging/usr/bin/$package" <<'LAUNCHER'
#!/usr/bin/python3
"""Запуск установленного пакета."""
import sys

sys.path.insert(0, "/usr/lib/vpn-connect-monitoring")

from vpnmon.cli import main

sys.exit(main())
LAUNCHER
chmod 755 "$staging/usr/bin/$package"

cat > "$staging/usr/share/applications/$package.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=VPN Connect Monitoring
Comment=Контроль подключения VPN в рабочее время
Exec=vpn-connect-monitoring
Icon=network-vpn
Terminal=false
Categories=Network;Monitor;Utility;
Keywords=vpn;network;monitor;
StartupNotify=false
DESKTOP
chmod 644 "$staging/usr/share/applications/$package.desktop"

cat > "$staging/usr/share/doc/$package/copyright" <<'COPYRIGHT'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: vpn-connect-monitoring
Source: https://github.com/antonim/vpn-connect-monitoring

Files: *
License: MIT
COPYRIGHT

# --- метаданные пакета ---------------------------------------------------
#
# GTK и индикатор вынесены в Recommends, а не Depends: на сервере нужен
# только режим --daemon, тянуть туда полтора десятка библиотек рабочего
# стола незачем. Apt в Ubuntu ставит Recommends по умолчанию, поэтому на
# настольной машине всё приедет само.

cat > "$staging/DEBIAN/control" <<CONTROL
Package: $package
Version: $version
Section: net
Priority: optional
Architecture: all
Maintainer: antonim <495260+antonim@users.noreply.github.com>
Depends: python3 (>= 3.8), libnotify-bin
Recommends: python3-gi, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, pulseaudio-utils
Homepage: https://github.com/antonim/vpn-connect-monitoring
Description: Контроль подключения VPN в рабочее время
 Следит за тем, что VPN поднят в заданные часы и дни, предупреждает
 уведомлением со звуком при обрыве и ведёт журнал состояния.
 .
 По журналу строится HTML-отчёт: лента подключения, доступность
 в процентах и таблица обрывов с длительностью.
 .
 Работает значком в трее либо фоновым процессом без графики.
CONTROL

# --- сборка --------------------------------------------------------------

mkdir -p "$outdir"
deb="$outdir/${package}_${version}_all.deb"

# --root-owner-group избавляет от необходимости fakeroot.
dpkg-deb --root-owner-group --build "$staging" "$deb" >/dev/null

echo "Готово: $deb ($(du -h "$deb" | cut -f1))"

if command -v lintian >/dev/null 2>&1; then
    echo "--- lintian ---"
    lintian --no-tag-display-limit "$deb" || true
fi
