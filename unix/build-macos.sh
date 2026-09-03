#!/bin/bash
#
# Сборка архива для macOS: vpn-connect-monitoring-<версия>-macos.tar.gz
#
# Внутри — код, launcher и install.sh, который раскладывает всё в ~/.local
# и не требует sudo. Формат выбран вместо .pkg сознательно: pkgbuild есть
# только на macOS, а архив собирается где угодно, в том числе в CI.
# Кому нужен именно .pkg — см. build-pkg.sh, он запускается на Mac.
#
# Использование:  ./build-macos.sh [каталог-вывода]

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

root="$staging/$package-$version"
mkdir -p "$root/lib/vpnmon" "$root/bin"

cp "$here/src/vpnmon/"*.py "$root/lib/vpnmon/"

cat > "$root/bin/$package" <<'LAUNCHER'
#!/usr/bin/env python3
"""Запуск установленной копии."""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(here), "lib"))

from vpnmon.cli import main

sys.exit(main())
LAUNCHER
chmod 755 "$root/bin/$package"

cat > "$root/install.sh" <<'INSTALL'
#!/bin/bash
#
# Установка в ~/.local — без sudo и без записи в системные каталоги.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
prefix="${PREFIX:-$HOME/.local}"

echo "Установка в $prefix"

mkdir -p "$prefix/lib" "$prefix/bin"
rm -rf "$prefix/lib/vpnmon"
cp -R "$here/lib/vpnmon" "$prefix/lib/vpnmon"
cp "$here/bin/vpn-connect-monitoring" "$prefix/bin/"
chmod 755 "$prefix/bin/vpn-connect-monitoring"

echo "Готово."

case ":$PATH:" in
    *":$prefix/bin:"*)
        ;;
    *)
        echo
        echo "ВНИМАНИЕ: $prefix/bin отсутствует в PATH."
        echo "Чтобы команда была доступна в терминале, добавьте в ~/.zshrc:"
        echo "    export PATH=\"\$PATH:$prefix/bin\""
        echo "На автозапуск это не влияет — он использует полный путь."
        ;;
esac

echo
echo "Дальше:"
echo "    $prefix/bin/vpn-connect-monitoring --list     # посмотреть подключения"
echo "    $prefix/bin/vpn-connect-monitoring            # запустить"
INSTALL
chmod 755 "$root/install.sh"

cat > "$root/README.txt" <<'READ'
VPN Connect Monitoring для macOS

Установка:
    ./install.sh

Удаление:
    rm -rf ~/.local/lib/vpnmon ~/.local/bin/vpn-connect-monitoring
    launchctl unload -w ~/Library/LaunchAgents/io.github.antonim.vpn-connect-monitoring.plist
    rm -f ~/Library/LaunchAgents/io.github.antonim.vpn-connect-monitoring.plist

Настройки и журнал: ~/.config/vpn-connect-monitoring/

Требуется python3 с PyObjC — он входит в состав Command Line Tools:
    xcode-select --install

Подробности: https://github.com/antonim/vpn-connect-monitoring
READ

mkdir -p "$outdir"
archive="$outdir/$package-$version-macos.tar.gz"
tar -czf "$archive" -C "$staging" "$package-$version"

echo "Готово: $archive ($(du -h "$archive" | cut -f1))"
