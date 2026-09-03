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
#!/bin/sh
#
# Запуск установленной копии.
#
# Интерпретатор выбирается не через `env python3`, а перебором: значок
# в строке меню требует PyObjC, а он есть только в системном
# /usr/bin/python3. Если в PATH первым стоит питон из Homebrew или pyenv
# — а так бывает часто — PyObjC там отсутствует, и значок не поднимется.
#
# Порядок: сначала любой питон, где PyObjC действительно импортируется,
# затем системный, затем что найдётся. Режимы --daemon, --list и --report
# работают без PyObjC, поэтому запуск не блокируем.

here=$(cd "$(dirname "$0")" && pwd)
lib=$(dirname "$here")/lib
export PYTHONPATH="$lib${PYTHONPATH:+:$PYTHONPATH}"

for py in /usr/bin/python3 python3 python3.13 python3.12 python3.11; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import objc' >/dev/null 2>&1; then
        exec "$py" -m vpnmon "$@"
    fi
done

for py in /usr/bin/python3 python3; do
    if command -v "$py" >/dev/null 2>&1; then
        exec "$py" -m vpnmon "$@"
    fi
done

echo "python3 не найден." >&2
exit 127
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

# Диагностический скрипт кладём в архив: без него человек, у которого
# что-то не заработало, не сможет ничего внятного сообщить.
cp "$here/tools/macos-check.sh" "$root/macos-check.sh"
chmod 755 "$root/macos-check.sh"

cat > "$root/README.txt" <<'READ'
VPN Connect Monitoring для macOS

Эта сборка НЕ ПРОВЕРЯЛАСЬ на живой macOS: разрабатывалась она на другой
системе. Общая логика протестирована, специфика macOS — нет.

Если что-то не работает, запустите диагностику и пришлите её вывод:
    bash macos-check.sh

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
