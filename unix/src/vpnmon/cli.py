"""Точка входа и разбор аргументов.

Режима два. `--tray` — значок в трее, обычный настольный сценарий.
`--daemon` — тот же наблюдатель без графики: годится для машины без
рабочего стола и для запуска из systemd. GTK в этом режиме не импортируется
вовсе, поэтому python3-gi там не нужен.
"""

import argparse
import datetime
import os
import signal
import sys
import time

from . import APP_ID, APP_TITLE, __version__


def _cmd_list():
    from . import vpn

    targets = vpn.list_targets()
    if not targets:
        print("VPN-подключений не найдено.")
        if sys.platform == "darwin":
            print("Ищутся службы из «Системных настроек» (scutil --nc)")
            print("и интерфейсы utun с назначенным адресом.")
        else:
            print("Ищутся интерфейсы wg*/tun*/tap*/ppp* и подключения NetworkManager.")
        return 1

    print("Найденные подключения (значение для VpnTarget в конфиге):")
    for target in targets:
        state = "поднято" if vpn.is_connected(target.key) else "не поднято"
        print("  %-28s %-44s %s" % (target.key, target.label, state))
    return 0


def _cmd_report(path, open_it):
    from . import report

    written = report.write(path)
    print("Отчёт: %s" % written)

    if open_it:
        import shutil
        import subprocess

        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, written],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print("xdg-open не найден — откройте файл вручную.")
    return 0


def _cmd_daemon():
    from . import history
    from .config import Config
    from .monitor import Monitor

    config = Config.load()
    if not config.vpn_target:
        print("VPN-подключение не выбрано. Посмотрите список:  %s --list" % APP_ID,
              file=sys.stderr)
        return 2

    history.prune()
    monitor = Monitor(config)

    stopping = {"now": False}

    def _stop(_signum, _frame):
        stopping["now"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    print("%s: наблюдение за %s, интервал %d с"
          % (APP_TITLE, config.vpn_target, config.interval_seconds))

    last_state = None
    while not stopping["now"]:
        state = monitor.tick()
        if state != last_state:
            print("%s  %s" % (datetime.datetime.now().strftime("%H:%M:%S"), monitor.detail))
            sys.stdout.flush()
            last_state = state

        # Спим короткими отрезками, иначе сигнал завершения ждал бы
        # до конца интервала опроса.
        for _ in range(max(1, config.interval_seconds)):
            if stopping["now"]:
                break
            time.sleep(1)

    monitor.shutdown()
    print("Остановлено.")
    return 0


def _cmd_tray(open_settings):
    if sys.platform == "darwin":
        try:
            from . import tray_macos
        except (ImportError, ValueError) as exc:
            print("Не удалось загрузить значок строки меню: %s" % exc, file=sys.stderr)
            print("Нужен PyObjC — он входит в состав системного python3,", file=sys.stderr)
            print("который ставится вместе с Command Line Tools:", file=sys.stderr)
            print("    xcode-select --install", file=sys.stderr)
            print("Либо запустите фоновый режим:  %s --daemon" % APP_ID, file=sys.stderr)
            return 2

        try:
            tray_macos.run(open_settings=open_settings)
        except KeyboardInterrupt:
            pass
        return 0

    try:
        from .tray_gtk import TrayApp
    except (ImportError, ValueError) as exc:
        print("Не удалось загрузить графическую часть: %s" % exc, file=sys.stderr)
        print("Установите python3-gi и gir1.2-ayatanaappindicator3-0.1,", file=sys.stderr)
        print("либо запустите фоновый режим:  %s --daemon" % APP_ID, file=sys.stderr)
        return 2

    app = TrayApp(open_settings=open_settings)
    try:
        app.run()
    except KeyboardInterrupt:
        app.quit()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=APP_ID,
        description="Контроль подключения VPN в рабочее время.",
    )
    parser.add_argument("--tray", action="store_true",
                        help="значок в трее без открытия настроек (для автозапуска)")
    parser.add_argument("--daemon", action="store_true",
                        help="фоновый режим без графики")
    parser.add_argument("--list", action="store_true",
                        help="показать найденные VPN-подключения")
    parser.add_argument("--report", nargs="?", const="", metavar="ФАЙЛ",
                        help="построить HTML-отчёт по журналу")
    parser.add_argument("--open", action="store_true",
                        help="открыть отчёт в браузере (вместе с --report)")
    parser.add_argument("--version", action="version",
                        version="%s %s" % (APP_TITLE, __version__))

    args = parser.parse_args(argv)

    if args.list:
        return _cmd_list()

    if args.report is not None:
        return _cmd_report(args.report or None, args.open)

    if args.daemon:
        return _cmd_daemon()

    # Без аргументов открываем настройки: при первом запуске человек должен
    # увидеть, где выбирается подключение.
    return _cmd_tray(open_settings=not args.tray)


if __name__ == "__main__":
    sys.exit(main())
