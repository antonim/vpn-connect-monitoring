#!/bin/bash
#
# Установка в ~/.local — без sudo и без записи в системные каталоги.
#
# Ставится команда для терминала. Значок в строке меню живёт в пакете
# «VPN Connect Monitoring.app» рядом с этим скриптом и в установке не
# нуждается: его достаточно перенести в «Программы».

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
prefix="${PREFIX:-$HOME/.local}"
app="VPN Connect Monitoring.app"

fail=0

# --- проверка окружения ---------------------------------------------------

echo "== Проверка окружения =="

if [ "$(uname -s)" != "Darwin" ]; then
    echo "  Это сборка для macOS, а система — $(uname -s)."
    exit 1
fi
echo "  macOS $(sw_vers -productVersion 2>/dev/null || echo '?') $(uname -m)"

# Тот же перебор, что и в запускающих скриптах: /usr/bin/python3 без
# Command Line Tools — заглушка, открывающая окно установки, поэтому
# трогаем её последней и только при установленных инструментах.
python=""
for py in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 2>/dev/null)"; do
    [ -n "$py" ] && [ -x "$py" ] || continue
    [ "$py" = /usr/bin/python3 ] && continue
    "$py" -c 'import ctypes' >/dev/null 2>&1 && { python="$py"; break; }
done
if [ -z "$python" ] && xcode-select -p >/dev/null 2>&1 && [ -x /usr/bin/python3 ]; then
    /usr/bin/python3 -c 'import ctypes' >/dev/null 2>&1 && python=/usr/bin/python3
fi

if [ -z "$python" ]; then
    echo "  python3: НЕ НАЙДЕН"
    echo
    echo "Программе нужен python3. Поставьте его любым способом:"
    echo "    xcode-select --install                 # инструменты Apple"
    echo "    brew install python3                   # если есть Homebrew"
    echo "    https://www.python.org/downloads/macos/"
    echo
    echo "После установки запустите ./install.sh ещё раз."
    exit 1
fi
echo "  python3: $python ($("$python" --version 2>&1))"

# Значку нужен AppKit через ctypes. Сторонних библиотек не требуется,
# но проверить, что мост поднимается, дешевле здесь, чем ловить это
# при первом запуске.
if PYTHONPATH="$here/lib" "$python" -c 'import vpnmon.objc_bridge' >/dev/null 2>&1; then
    echo "  AppKit через ctypes: доступен"
else
    echo "  AppKit через ctypes: НЕТ — значок в строке меню не поднимется"
    echo "    (фоновый режим --daemon при этом работает)"
    fail=1
fi

for cmd in scutil ifconfig osascript afplay open launchctl; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "  нет утилиты $cmd"; fail=1; }
done

# --- установка ------------------------------------------------------------

echo
echo "== Установка =="
set -e
echo "  команда -> $prefix/bin/vpn-connect-monitoring"

mkdir -p "$prefix/lib" "$prefix/bin"
rm -rf "$prefix/lib/vpnmon"
cp -R "$here/lib/vpnmon" "$prefix/lib/vpnmon"
# Кэш байт-кода мог остаться от другой версии питона.
rm -rf "$prefix/lib/vpnmon/__pycache__"
cp "$here/bin/vpn-connect-monitoring" "$prefix/bin/"
chmod 755 "$prefix/bin/vpn-connect-monitoring"
set +e

# В архиве приложение лежит рядом со скриптом, а на образе диска —
# уровнем выше: там install.sh убран в подпапку «Для терминала», чтобы
# в главном окне остались только пакет и ярлык «Программы».
appdir=""
for candidate in "$here/$app" "$here/../$app"; do
    [ -d "$candidate" ] && { appdir="$candidate"; break; }
done

if [ -n "$appdir" ]; then
    target="$HOME/Applications/$app"
    if [ -t 0 ]; then
        printf '  Перенести «%s» в ~/Applications? [Y/n] ' "$app"
        read -r answer
    else
        answer="n"
    fi
    case "${answer:-y}" in
        [YyДд]*|"")
            mkdir -p "$HOME/Applications"
            rm -rf "$target"
            cp -R "$appdir" "$target"
            echo "  приложение -> $target"

            # Регистрация в LaunchServices: без неё центр уведомлений
            # не знает такого приложения и молча выбрасывает его
            # сообщения. Обычно регистрация происходит при первом
            # запуске из Finder, но полагаться на это не стоит.
            lsregister=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
            [ -x "$lsregister" ] && "$lsregister" -f "$target" 2>/dev/null \
                && echo "  зарегистрировано в системе"

            # Архив, скачанный браузером и распакованный в Finder,
            # помечен карантином, и Gatekeeper при первом запуске
            # заблокирует программу. Снять метку — решение человека,
            # поэтому спрашиваем, а не делаем молча.
            if xattr -p com.apple.quarantine "$target" >/dev/null 2>&1; then
                echo
                echo "  На приложении стоит метка карантина: macOS при первом"
                echo "  запуске сообщит, что не может проверить программу."
                if [ -t 0 ]; then
                    printf '  Снять метку сейчас? [Y/n] '
                    read -r unquarantine
                else
                    unquarantine="n"
                fi
                case "${unquarantine:-y}" in
                    [YyДд]*|"")
                        xattr -dr com.apple.quarantine "$target" \
                            && echo "  метка снята"
                        ;;
                    *)
                        echo "  оставлено; как разрешить запуск — написано в README.txt"
                        ;;
                esac
            fi
            ;;
        *)
            echo "  приложение оставлено на месте: $appdir"
            ;;
    esac
fi

echo
if [ "$fail" -ne 0 ]; then
    echo "Установлено, но с замечаниями выше."
else
    echo "Готово."
fi

case ":$PATH:" in
    *":$prefix/bin:"*)
        ;;
    *)
        echo
        echo "ВНИМАНИЕ: $prefix/bin отсутствует в PATH."
        echo "Чтобы команда была доступна в терминале, добавьте в ~/.zshrc:"
        echo "    export PATH=\"\$PATH:$prefix/bin\""
        echo "На значок и автозапуск это не влияет — они используют полный путь."
        ;;
esac

echo
echo "Дальше:"
echo "    запустите «VPN Connect Monitoring» из Launchpad или Программ,"
echo "    выберите подключение в открывшемся файле настроек"
echo "    и включите «Запускать при входе в систему» в меню значка."
echo
echo "Из терминала:"
echo "    $prefix/bin/vpn-connect-monitoring --list     # посмотреть подключения"
echo "    $prefix/bin/vpn-connect-monitoring --daemon   # фоновый режим без значка"
