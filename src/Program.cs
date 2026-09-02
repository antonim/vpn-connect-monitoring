using System;
using System.Threading;
using System.Windows.Forms;

namespace VpnConnectMonitoring
{
    static class Program
    {
        const string MutexName = "VpnConnectMonitoring.SingleInstance";
        const string ShowEventName = "VpnConnectMonitoring.ShowSettings";

        [STAThread]
        static void Main(string[] args)
        {
            bool trayOnly = false;
            for (int i = 0; i < args.Length; i++)
            {
                if (string.Equals(args[i], "--tray", StringComparison.OrdinalIgnoreCase))
                    trayOnly = true;
            }

            bool createdNew;
            using (Mutex mutex = new Mutex(true, MutexName, out createdNew))
            {
                EventWaitHandle showSignal = new EventWaitHandle(
                    false, EventResetMode.AutoReset, ShowEventName);

                if (!createdNew)
                {
                    // Приложение уже в трее: просим его открыть настройки
                    // и молча выходим, чтобы не плодить значки.
                    showSignal.Set();
                    return;
                }

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);

                // Автозапуск передаёт --tray и окно не открывает. Ручной запуск
                // из папки загрузок, наоборот, сразу показывает настройки —
                // там же находится кнопка установки.
                bool openSettings = !trayOnly;

                Application.Run(new TrayApp(openSettings, showSignal));

                GC.KeepAlive(mutex);
            }
        }
    }
}
