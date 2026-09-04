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

# Ищем код: рядом в lib/ (архив), внутри пакета .app, или в src/ (репозиторий)
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

line "Python"
# Значку нужен только AppKit через ctypes — он входит в стандартную
# библиотеку, сторонних пакетов не требуется. Проверяем каждый найденный
# интерпретатор отдельно.
#
# /usr/bin/python3 разбираем последним: без Command Line Tools это
# заглушка, которая при вызове открывает окно установки на полтора
# гигабайта, поэтому сначала спрашиваем xcode-select.
check_python() {
    local py="$1"
    local ver state
    ver="$("$py" --version 2>&1)"
    if "$py" -c 'import vpnmon.objc_bridge' >/dev/null 2>&1; then
        state="AppKit доступен"
    elif "$py" -c 'import ctypes' >/dev/null 2>&1; then
        state="ctypes есть, AppKit НЕ поднялся"
    else
        state="не работает"
    fi
    printf '  %-32s %-16s %s\n' "$py" "$ver" "$state"
}

# Порядок перебора тот же, что в запускающих скриптах, и выбранный
# интерпретатор здесь тот же, каким программа будет работать на самом
# деле: диагностика, проверяющая не то, что запускается, бесполезна.
#
# Обойтись без конвейера (| sort) здесь важно: он выполняет цикл в
# подоболочке, и выбранный питон до основного скрипта не доходит.
PY=""
seen=""
for py in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
          "$(command -v python3 2>/dev/null)" /usr/bin/python3; do
    [ -n "$py" ] && [ -x "$py" ] || continue
    case " $seen " in *" $py "*) continue ;; esac
    seen="$seen $py"

    if [ "$py" = /usr/bin/python3 ] && ! xcode-select -p >/dev/null 2>&1; then
        echo "  /usr/bin/python3                 нет Command Line Tools (заглушка, не трогаем)"
        continue
    fi

    check_python "$py"
    if [ -z "$PY" ] && "$py" -c 'import ctypes' >/dev/null 2>&1; then
        PY="$py"
    fi
done

echo
if [ -z "$PY" ]; then
    echo "  python3 не найден — дальше проверять нечем."
    echo "  Поставьте его:  xcode-select --install"
    exit 1
fi
echo "  проверки ниже выполняются через: $PY"

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
"$PY" -m vpnmon --version 2>&1
echo
"$PY" -m vpnmon --list 2>&1

line "Проверка уведомления"
echo "Сейчас должно появиться уведомление. Видно ли его?"
"$PY" - <<'PY' 2>&1
from vpnmon import notify

print("путь доставки: %s" % notify.backend())
ok = notify.show("Проверка", "Если вы это видите — уведомления работают.", critical=True)
print("вызов вернул: %s" % ok)
print()
print("ВАЖНО: True здесь означает лишь, что запрос принят. Показала ли")
print("macOS уведомление на самом деле, программа узнать не может.")
print("Если ничего не появилось — Системные настройки -> Уведомления,")
print("найдите «VPN Connect Monitoring», включите «Допуск уведомлений»")
print("и выберите стиль «Предупреждения»: «Баннеры» гаснут сами, и обрыв")
print("связи легко пропустить.")
PY

line "Проверка звука"
echo "Сейчас должен прозвучать сигнал из трёх нисходящих тонов. Слышно?"
"$PY" - <<'PY' 2>&1
from vpnmon import sound
print("проигрыватель найден: %s" % sound.available())
print("вызов вернул: %s" % sound.play_alarm())
PY
sleep 3

line "Построение отчёта"
"$PY" -m vpnmon --report /tmp/vpnmon-check-report.html 2>&1
ls -la /tmp/vpnmon-check-report.html 2>&1

line "Значок в строке меню"
# Значок создаётся по-настоящему, но без запуска цикла событий: так
# проверяется всё, что может сломаться, и программа не остаётся висеть.
#
# Настройки на время проверки подменяются копией во временном каталоге:
# создание значка пишет журнал и, при первом запуске, сам конфиг, а
# диагностика ничего в профиле менять не должна.
sandbox="$(mktemp -d)"
mkdir -p "$sandbox/vpn-connect-monitoring"
if [ -f "$HOME/.config/vpn-connect-monitoring/config.ini" ]; then
    cp "$HOME/.config/vpn-connect-monitoring/config.ini" \
       "$sandbox/vpn-connect-monitoring/" 2>/dev/null
    echo "  (настройки взяты из профиля, записи идут во временный каталог)"
else
    echo "  (настроек в профиле нет — проверяется значок без выбранного подключения)"
fi
XDG_CONFIG_HOME="$sandbox" "$PY" - <<'PY' 2>&1
try:
    from vpnmon import tray_macos
    from vpnmon.objc_bridge import NSInteger, cls, msg, pystring

    app = msg(cls("NSApplication"), "sharedApplication")
    msg(app, "setActivationPolicy:", 1, argtypes=[NSInteger])

    tray = tray_macos.MenuBarApp(open_settings=False)
    button = msg(tray.status_item, "button")
    title = pystring(msg(button if button else tray.status_item, "title"))
    count = msg(tray.menu, "numberOfItems", restype=NSInteger)
    print("значок создан, заголовок %r, пунктов в меню: %d" % (title, count))
    print("состояние: %s" % tray.monitor.detail)
except Exception as exc:
    print("ОШИБКА -> %s: %s" % (type(exc).__name__, exc))
    import traceback
    traceback.print_exc()
PY
rm -rf "$sandbox"

line "Регистрация приложения"
# Уведомления приходят от имени программы только пока в системе
# зарегистрирована ровно одна копия пакета. Если копий несколько —
# например, старая версия осталась в Корзине после обновления, —
# центр уведомлений выбирает среди них и, попав на нерабочую,
# показывает сообщения от имени «Python».
LSR=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
if [ -x "$LSR" ]; then
    echo "  поиск зарегистрированных копий, это занимает несколько секунд…"
    copies="$("$LSR" -dump 2>/dev/null \
        | grep "^path:.*VPN Connect Monitoring.app" \
        | sed 's/path: *//; s/ (0x.*//')"
    count="$(printf '%s' "$copies" | grep -c . )"
    if [ "$count" -eq 0 ]; then
        echo "  ни одной копии не зарегистрировано"
        echo "  (уведомления будут приходить от имени «Python»)"
    else
        printf '%s\n' "$copies" | sed 's/^/    /'
        if [ "$count" -gt 1 ]; then
            echo
            echo "  ВНИМАНИЕ: копий больше одной — уведомления могут приходить"
            echo "  от имени «Python». Удалите лишние, включая те, что лежат"
            echo "  в Корзине, очистите её и запустите ./install.sh заново."
        fi
    fi
else
    echo "  lsregister не найден"
fi

line "Автозапуск"
"$PY" - <<'PY' 2>&1
from vpnmon import autostart
print("файл агента: %s" % autostart.path())
print("включён: %s" % autostart.enabled())
args, root = autostart._command_parts()
print("будет запускать: %s" % " ".join(args))
PY

line "Готово"
echo "Пришлите весь вывод выше, а также ответы:"
echo "  1. Появилось ли уведомление?"
echo "  2. Был ли слышен звук?"
echo "  3. Если запускали программу целиком — появился ли значок в строке меню?"
