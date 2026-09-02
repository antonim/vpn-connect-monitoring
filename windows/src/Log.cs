using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace VpnConnectMonitoring
{
    // Диагностический журнал в %APPDATA%\VpnConnectMonitoring\debug.log.
    //
    // Показ уведомления — операция без обратной связи: Show() возвращает void
    // и не бросает исключений, когда система отбрасывает уведомление. Поэтому
    // единственный способ отличить «код не выполнился» от «выполнился, но
    // система его проигнорировала» — фиксировать каждый шаг здесь.
    public static class Log
    {
        const long MaxBytes = 512 * 1024;
        static readonly object gate = new object();

        public static string FilePath
        {
            get { return Path.Combine(Config.Dir, "debug.log"); }
        }

        public static void Write(string message)
        {
            lock (gate)
            {
                try
                {
                    Directory.CreateDirectory(Config.Dir);

                    // Файл диагностики не должен разрастаться без предела.
                    FileInfo fi = new FileInfo(FilePath);
                    if (fi.Exists && fi.Length > MaxBytes)
                        File.Delete(FilePath);

                    File.AppendAllText(FilePath,
                        DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture)
                            + "  " + message + Environment.NewLine,
                        Encoding.UTF8);
                }
                catch { }
            }
        }
    }
}
