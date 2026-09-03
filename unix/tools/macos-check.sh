#!/bin/bash
#
# Диагностика macOS-версии: собирает в один вывод всё, что нужно, чтобы
# понять, работает ли определение VPN, уведомления, звук и значок.
#
# Запускать на Mac из распакованного архива:
#     bash macos-check.sh
#
# Скрипт ничего не устанавливает и не меняет, кроме одного пробного
# уведомления и одного звукового сигнала.
#
# ВНИМАНИЕ: в выводе будут видны имена ваших VPN-подключений. Если они
# чувствительные, замените их перед отправкой.

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ищем код: рядом в lib/ (архив) или в src/ (репозиторий)
if [ -d "$here/lib/vpnmon" ]; then
    pylib="$here/lib"
elif [ -d "$here/../src/vpnmon" ]; then
    pylib="$(cd "$here/../src" && pwd)"
elif [ -d "$here/src/vpnmon" ]; then
    pylib="$here/src"
else
    echo "Не найден каталог vpnmon рядом со скриптом." >&2
    exit 1
fi

export PYTHONPATH="$pylib"

line() { printf '\n===== %s =====\n' "$1"; }

line "Система"
sw_vers 2>/dev/null || echo "sw_vers недоступен"
echo "arch: $(uname -m)"

line "Python и PyObjC"
# Проверяем каждый найденный интерпретатор отдельно: PyObjC входит только
# в системный /usr/bin/python3, а в PATH часто первым стоит Homebrew или
# pyenv, где его нет.
for py in /usr/bin/python3 "$(command -v python3 2>/dev/null)" \
          "$(command -v python3.13 2>/dev/null)" "$(command -v python3.12 2>/dev/null)"; do
    [ -n "$py" ] && [ -x "$py" ] || continue
    ver="$("$py" --version 2>&1)"
    if "$py" -c 'import objc, AppKit' >/dev/null 2>&1; then
        objc_state="PyObjC ЕСТЬ"
    else
        objc_state="PyObjC нет"
    fi
    printf '  %-28s %-16s %s\n' "$py" "$ver" "$objc_state"
done | sort -u

echo
echo "  какой выбирает PATH: $(command -v python3 || echo 'НЕ НАЙДЕН')"

line "Внешние утилиты"
for cmd in scutil ifconfig osascript afplay terminal-notifier open launchctl; do
    path="$(command -v "$cmd" 2>/dev/null)"
    printf '  %-18s %s\n' "$cmd" "${path:-НЕТ}"
done

line "scutil --nc list (сырой вывод)"
scutil --nc list 2>&1 || echo "команда не отработала"

line "Интерфейсы utun/ppp/ipsec"
for name in $(ifconfig -l 2>/dev/null); do
    case "$name" in
        utun*|ppp*|ipsec*|tun*|tap*)
            has_inet="нет адреса"
            ifconfig "$name" 2>/dev/null | grep -q 'inet ' && has_inet="есть адрес"
            flags="$(ifconfig "$name" 2>/dev/null | sed -n '1s/.*flags=[0-9]*<\([^>]*\)>.*/\1/p')"
            printf '  %-10s %-12s flags=%s\n' "$name" "$has_inet" "$flags"
            ;;
    esac
done

line "Что увидела программа"
python3 -m vpnmon --version 2>&1
echo
python3 -m vpnmon --list 2>&1

line "Проверка уведомления"
echo "Сейчас должно появиться уведомление. Видно ли его?"
python3 - <<'PY' 2>&1
from vpnmon import notify
ok = notify.show("Проверка", "Если вы это видите — уведомления работают.", critical=True)
print("вызов вернул: %s" % ok)
PY

line "Проверка звука"
echo "Сейчас должен прозвучать сигнал из трёх нисходящих тонов. Слышно?"
python3 - <<'PY' 2>&1
from vpnmon import sound
print("проигрыватель найден: %s" % sound.available())
print("вызов вернул: %s" % sound.play_alarm())
PY
sleep 3

line "Построение отчёта"
python3 -m vpnmon --report /tmp/vpnmon-check-report.html 2>&1
ls -la /tmp/vpnmon-check-report.html 2>&1

line "Значок в строке меню (только импорт, без запуска)"
python3 - <<'PY' 2>&1
try:
    from vpnmon import tray_macos
    print("модуль импортируется, класс: %s" % tray_macos.MenuBarApp)
except Exception as exc:
    print("ОШИБКА -> %s: %s" % (type(exc).__name__, exc))
    import traceback
    traceback.print_exc()
PY

line "Готово"
echo "Пришлите весь вывод выше, а также ответы:"
echo "  1. Появилось ли уведомление?"
echo "  2. Был ли слышен звук?"
echo "  3. Если запускали программу целиком — появился ли значок в строке меню?"
