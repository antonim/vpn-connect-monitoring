#!/bin/bash
#
# Сборка для macOS: образ диска и архив.
#
#   vpn-connect-monitoring-<версия>-macos.dmg      основной способ раздачи
#   vpn-connect-monitoring-<версия>-macos.tar.gz   для тех, кто в терминале
#
# В образе — приложение и ярлык «Программы» рядом: человек перетаскивает
# одно в другое. Всё для терминала убрано в подпапку, чтобы в главном окне
# лежали две вещи, между которыми перетаскивают.
#
# ВАЖНО: скрипт работает только на macOS, в отличие от build-deb.sh.
# Пакет .app требует osacompile, codesign, sips, iconutil и hdiutil —
# все они входят в macOS, но нигде больше их нет. Собрать macOS-сборку
# в линуксовом CI больше нельзя.
#
# Использование:  ./build-macos.sh [каталог-вывода]

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
outdir="${1:-$here/build}"

package="vpn-connect-monitoring"
app="VPN Connect Monitoring.app"

version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$here/src/vpnmon/__init__.py")"
if [ -z "$version" ]; then
    echo "Не удалось прочитать версию из src/vpnmon/__init__.py" >&2
    exit 1
fi

for tool in osacompile codesign hdiutil sips iconutil; do
    command -v "$tool" >/dev/null \
        || { echo "нет $tool — сборка возможна только на macOS" >&2; exit 1; }
done

staging="$(mktemp -d)"
dmgstage=""
trap 'rm -rf "$staging" "$dmgstage"' EXIT

root="$staging/$package-$version"
mkdir -p "$root/bin" "$root/lib"

copy_package() {
    # Кэш байт-кода привязан к версии питона сборочной машины, а .DS_Store
    # к раздаче отношения не имеет — в архив не попадает ни то, ни другое.
    rsync -a --exclude '__pycache__' --exclude '.DS_Store' \
        "$here/src/vpnmon/" "$1/vpnmon/"
}

# В README номер версии стоит в примерах команд — подставляем его при
# сборке, чтобы не забыть обновить руками.
#
# Проверка не лишняя: если README случайно заменят копией из собранного
# архива, подстановка исчезнет вместе с ней, и в новой сборке останется
# чужой номер версии — молча и незаметно.
grep -q '@VERSION@' "$here/macos/README.txt" \
    || { echo "в macos/README.txt нет @VERSION@ — версия зашита намертво" >&2; exit 1; }
sed "s/@VERSION@/$version/g" "$here/macos/README.txt" > "$root/README.txt"

cp "$here/macos/install.sh" "$root/install.sh"
cp "$here/tools/macos-check.sh" "$root/macos-check.sh"
cp "$here/macos/launcher" "$root/bin/$package"
copy_package "$root/lib"

# --- пакет .app -----------------------------------------------------------
#
# Пакет строится вокруг стандартного applet'а: исполняемым файлом .app
# обязан быть Mach-O, а не скрипт. macOS 15 приложение со скриптом на
# этом месте не открывает вовсе — сначала предлагает поставить Rosetta,
# не сумев определить архитектуру, потом возвращает -10669. Компилировать
# ничего не приходится: osacompile входит в macOS и собирает пакет вокруг
# applet'а, готового под обе архитектуры.

bundle="$root/$app"
osacompile -o "$bundle" "$here/macos/applet.applescript"

contents="$bundle/Contents"
mkdir -p "$contents/Resources/lib"

cp "$here/macos/launcher" "$contents/Resources/$package"
# Имя launcher оставляем ссылкой: applet зовёт его по этому пути,
# а понятное имя нужно тем, кто полезет внутрь пакета руками.
ln -sf "$package" "$contents/Resources/launcher"
copy_package "$contents/Resources/lib"

# Значок рисуется здесь же, а не хранится в репозитории готовым: скрипт
# весит несколько килобайт против сотни у .icns, и рисунок не может
# разойтись с кодом, который его создаёт.
if python3 "$here/macos/make-icon.py" "$contents/Resources/AppIcon.icns"; then
    rm -f "$contents/Resources/applet.icns"
    icon_key="AppIcon"
else
    echo "ВНИМАНИЕ: значок собрать не удалось, останется стандартный" >&2
    icon_key="applet"
fi

# Info.plist берём тот, что сделал osacompile, и дописываем своё:
# заменить его целиком нельзя — там есть ключи, без которых applet
# не запустится.
plist="$contents/Info.plist"
set_plist() {  # ключ тип значение
    plutil -replace "$1" "-$2" "$3" "$plist" 2>/dev/null \
        || plutil -insert "$1" "-$2" "$3" "$plist"
}
set_plist CFBundleIdentifier         string "io.github.antonim.vpn-connect-monitoring"
set_plist CFBundleName               string "VPN Connect Monitoring"
set_plist CFBundleDisplayName        string "VPN Connect Monitoring"
set_plist CFBundleVersion            string "$version"
set_plist CFBundleShortVersionString string "$version"
set_plist CFBundleIconFile           string "$icon_key"
# Программа живёт в строке меню: ни значка в Dock, ни пункта
# в переключателе приложений ей не нужно.
set_plist LSUIElement                bool   true
# «Предупреждения» вместо «Баннеров»: баннер гаснет сам через несколько
# секунд, и обрыв связи легко пропустить. Ключ задаёт лишь значение по
# умолчанию при первой регистрации — выбор человека главнее.
set_plist NSUserNotificationAlertStyle string "alert"

# osacompile проставляет минимальную версию системы по архитектурам и
# перечисляет там один x86_64 — наследие времён, когда других вариантов
# не было. LaunchServices читает это буквально и заключает, что для
# arm64 приложение не годится: сначала предлагает поставить Rosetta,
# потом отказывается запускать с ошибкой -10669. Сам applet при этом
# собран под обе архитектуры, так что ключ просто лишний.
plutil -remove LSMinimumSystemVersionByArchitecture "$plist" 2>/dev/null || true

# Ещё osacompile вписывает объяснения для доступа к камере, контактам,
# фотографиям и прочему, чего эта программа не касается. Оставлять их
# нельзя: они всплывут в системных запросах приватности и будут пугать
# человека тем, чего не происходит.
for key in NSAppleMusicUsageDescription NSCalendarsUsageDescription \
           NSCameraUsageDescription NSContactsUsageDescription \
           NSHomeKitUsageDescription NSMicrophoneUsageDescription \
           NSPhotoLibraryUsageDescription NSRemindersUsageDescription \
           NSSiriUsageDescription NSSystemAdministrationUsageDescription; do
    plutil -remove "$key" "$plist" 2>/dev/null || true
done

chmod 755 "$root/install.sh" "$root/macos-check.sh" "$root/bin/$package" \
          "$contents/Resources/$package"
find "$root" -name '.DS_Store' -delete

# Правка Info.plist ломает подпись, которую ставит osacompile, а
# приложение со сломанной подписью macOS объявляет повреждённым
# и предлагает переместить в Корзину. Подписываем заново.
codesign --force --deep --sign - "$bundle" 2>/dev/null
codesign --verify "$bundle" || { echo "подпись пакета не прошла проверку" >&2; exit 1; }

# --- архив ----------------------------------------------------------------

mkdir -p "$outdir"
archive="$outdir/$package-$version-macos.tar.gz"
rm -f "$archive"
# COPYFILE_DISABLE=1 — иначе bsdtar кладёт рядом с каждым файлом
# служебные ._-файлы с ресурсными вилками.
COPYFILE_DISABLE=1 tar -czf "$archive" -C "$staging" "$package-$version"

# --- образ диска ----------------------------------------------------------
#
# Привычный для macOS способ раздачи: двойной щелчок открывает окно,
# где приложение перетаскивают на ярлык «Программы». Архив для этого
# не годится — из него человеку приходится тащить пакет вручную,
# догадываясь, куда именно.

dmgstage="$(mktemp -d)"
cp -R "$bundle" "$dmgstage/"
ln -s /Applications "$dmgstage/Applications"
cp "$root/README.txt" "$dmgstage/"

extra="$dmgstage/Для терминала"
mkdir "$extra"
cp -R "$root/bin" "$root/lib" "$extra/"
cp "$root/install.sh" "$root/macos-check.sh" "$extra/"

image="$outdir/$package-$version-macos.dmg"
rm -f "$image"
hdiutil create -quiet -volname "VPN Connect Monitoring $version" \
    -srcfolder "$dmgstage" -ov -format UDZO "$image"

echo "Готово:"
echo "  $image ($(du -h "$image" | cut -f1))"
echo "  $archive ($(du -h "$archive" | cut -f1))"
