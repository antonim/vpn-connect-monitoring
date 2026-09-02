# VPN Connect Monitoring — Linux

Следит за тем, что VPN поднят в рабочее время, предупреждает уведомлением
со звуком при обрыве и ведёт журнал, по которому строится отчёт с графиком.

Работает значком в трее либо фоновым процессом без графики.

## Установка

**[Скачать .deb](https://github.com/antonim/vpn-connect-monitoring/releases/latest)**, затем:

```bash
sudo apt install ./vpn-connect-monitoring_1.0.0_all.deb
```

Именно `apt`, а не `dpkg -i`: он сам подтянет зависимости.

Дальше запустить из меню приложений или командой:

```bash
vpn-connect-monitoring
```

Откроется окно настроек — выбрать своё подключение, при необходимости
поправить часы и дни, поставить галочку «Запускать при входе в систему».

## Выбор подключения

Список подключений приложение собирает само, вручную ничего искать не нужно.
Посмотреть, что оно видит, можно и из терминала:

```bash
vpn-connect-monitoring --list
```

Ищутся интерфейсы `wg*`, `tun*`, `tap*`, `ppp*` и подключения NetworkManager
типа `vpn`/`wireguard`. Подключения NetworkManager попадают в список даже
когда выключены — иначе выбрать нужное было бы нельзя.

В конфиге цель записывается с префиксом: `iface:wg0` или `nm:AVIA`.

## Режим без графики

Для машины без рабочего стола или для systemd:

```bash
vpn-connect-monitoring --daemon
```

GTK в этом режиме не импортируется вовсе, поэтому `python3-gi` не нужен.
Уведомления при этом всё равно отправляются, если в сессии есть
`notify-send`; журнал ведётся в любом случае.

Пример user-юнита `~/.config/systemd/user/vpn-connect-monitoring.service`:

```ini
[Unit]
Description=VPN Connect Monitoring
After=network.target

[Service]
ExecStart=/usr/bin/vpn-connect-monitoring --daemon
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now vpn-connect-monitoring
```

## Журнал и отчёт

Пункт **«Журнал подключения…»** в меню значка строит HTML-отчёт и открывает
его в браузере. То же самое из терминала:

```bash
vpn-connect-monitoring --report --open
```

В отчёте лента состояний за 24 часа, 3, 7 и 30 дней с переключением на
месте, доступность в процентах, суммарное и максимальное время без связи и
таблица обрывов. Файл самостоятельный — его можно переслать администратору.

Отчёт сделан в HTML, а не нарисован в окне GTK, намеренно: так он работает
и на машине без графики, и его удобно отправлять как есть.

## Файлы

| Путь | Что это |
|---|---|
| `~/.config/vpn-connect-monitoring/config.ini` | Настройки, обычный текст |
| `~/.config/vpn-connect-monitoring/history.csv` | Журнал, `дата-время;состояние` |
| `~/.config/vpn-connect-monitoring/report.html` | Последний построенный отчёт |
| `~/.config/autostart/vpn-connect-monitoring.desktop` | Автозапуск |

Формат конфига и журнала совпадает с Windows-версией.

## Сборка пакета

```bash
./build-deb.sh
```

Нужен только `dpkg-deb` из базовой Ubuntu. Пакет архитектурно-независимый:
внутри Python и текстовые файлы, компилировать нечего.

GTK и индикатор вынесены в `Recommends`, а не `Depends`: на сервере нужен
только `--daemon`, тянуть туда библиотеки рабочего стола незачем. Apt в
Ubuntu ставит `Recommends` по умолчанию, поэтому на настольной машине всё
приедет само.

## Отличия от Windows-версии

| | Windows | Linux |
|---|---|---|
| Состояние VPN | `NetworkInterface` | `/sys/class/net` + `nmcli` |
| Уведомления | WinRT + AppUserModelID | `notify-send` |
| Звук | `SoundPlayer` | `pw-play` / `paplay` / `aplay` |
| Значок | `NotifyIcon` | AppIndicator |
| Автозапуск | `HKCU\...\Run` | `~/.config/autostart` |
| График | окно WinForms | HTML-отчёт |

Две вещи, на которые стоит обратить внимание при доработке:

**Состояние интерфейса определяется по флагам, а не по `operstate`.**
У `tun`- и `wireguard`-интерфейсов `operstate` сплошь и рядом равен
`unknown` даже когда связь есть, и сравнение с `up` давало бы постоянную
ложную тревогу.

**Уведомления об обрыве отправляются с `--urgency critical`.** В GNOME такой
баннер висит, пока его не закроют. Исчезающий баннер — ровно та причина, по
которой обрывы пропускались в Windows-версии.
