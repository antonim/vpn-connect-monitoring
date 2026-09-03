using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace VpnConnectMonitoring
{
    // Настройки хранятся в %APPDATA%\VpnConnectMonitoring\config.ini — обычный текст
    // key=value, чтобы файл можно было при необходимости поправить руками
    // или раздать коллегам как готовый шаблон.
    public class Config
    {
        public string VpnName;
        public bool Enabled;
        public int IntervalSeconds;
        public int WorkStartMinutes;
        public int WorkEndMinutes;
        public bool[] Days;              // 0 = понедельник .. 6 = воскресенье
        public int RepeatSuppressMinutes;
        public bool NotifyOnRestore;
        public bool SoundEnabled;

        public Config()
        {
            // Пусто: конкретное подключение выбирает пользователь при первом
            // запуске. Подставлять сюда чьё-то имя нельзя — программа не
            // привязана ни к какому VPN.
            VpnName = "";
            Enabled = true;
            IntervalSeconds = 60;
            WorkStartMinutes = 9 * 60;
            WorkEndMinutes = 18 * 60;
            Days = new bool[] { true, true, true, true, true, false, false };
            RepeatSuppressMinutes = 15;
            NotifyOnRestore = true;
            SoundEnabled = true;
        }

        public static string Dir
        {
            get
            {
                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "VpnConnectMonitoring");
            }
        }

        public static string FilePath
        {
            get { return Path.Combine(Dir, "config.ini"); }
        }

        // Понедельник = 0, воскресенье = 6.
        public static int DayIndex(DayOfWeek dow)
        {
            return ((int)dow + 6) % 7;
        }

        public bool DayEnabled(DayOfWeek dow)
        {
            return Days[DayIndex(dow)];
        }

        // Окно может пересекать полночь (например 22:00–06:00). В этом случае
        // ночная половина относится к дню, когда окно началось, — иначе смена
        // с воскресенья на понедельник считалась бы неверно.
        public bool IsWithinSchedule(DateTime now)
        {
            int nowMin = now.Hour * 60 + now.Minute;

            if (WorkEndMinutes > WorkStartMinutes)
            {
                return DayEnabled(now.DayOfWeek)
                    && nowMin >= WorkStartMinutes
                    && nowMin < WorkEndMinutes;
            }

            if (nowMin >= WorkStartMinutes)
                return DayEnabled(now.DayOfWeek);
            if (nowMin < WorkEndMinutes)
                return DayEnabled(now.AddDays(-1).DayOfWeek);
            return false;
        }

        public Config Clone()
        {
            Config c = new Config();
            c.VpnName = VpnName;
            c.Enabled = Enabled;
            c.IntervalSeconds = IntervalSeconds;
            c.WorkStartMinutes = WorkStartMinutes;
            c.WorkEndMinutes = WorkEndMinutes;
            c.Days = (bool[])Days.Clone();
            c.RepeatSuppressMinutes = RepeatSuppressMinutes;
            c.NotifyOnRestore = NotifyOnRestore;
            c.SoundEnabled = SoundEnabled;
            return c;
        }

        public static Config Load()
        {
            Config c = new Config();
            try
            {
                if (!File.Exists(FilePath))
                    return c;

                foreach (string raw in File.ReadAllLines(FilePath, Encoding.UTF8))
                {
                    string line = raw.Trim();
                    if (line.Length == 0 || line[0] == '#' || line[0] == ';')
                        continue;

                    int eq = line.IndexOf('=');
                    if (eq <= 0)
                        continue;

                    string key = line.Substring(0, eq).Trim();
                    string val = line.Substring(eq + 1).Trim();

                    switch (key.ToLowerInvariant())
                    {
                        case "vpnname":
                            c.VpnName = val;
                            break;
                        case "enabled":
                            c.Enabled = ParseBool(val, c.Enabled);
                            break;
                        case "intervalseconds":
                            c.IntervalSeconds = ParseInt(val, c.IntervalSeconds, 10, 3600);
                            break;
                        case "workstartminutes":
                            c.WorkStartMinutes = ParseInt(val, c.WorkStartMinutes, 0, 1439);
                            break;
                        case "workendminutes":
                            c.WorkEndMinutes = ParseInt(val, c.WorkEndMinutes, 0, 1439);
                            break;
                        case "repeatsuppressminutes":
                            c.RepeatSuppressMinutes = ParseInt(val, c.RepeatSuppressMinutes, 0, 240);
                            break;
                        case "notifyonrestore":
                            c.NotifyOnRestore = ParseBool(val, c.NotifyOnRestore);
                            break;
                        case "soundenabled":
                            c.SoundEnabled = ParseBool(val, c.SoundEnabled);
                            break;
                        case "days":
                            string[] parts = val.Split(',');
                            if (parts.Length == 7)
                            {
                                for (int i = 0; i < 7; i++)
                                    c.Days[i] = ParseBool(parts[i].Trim(), c.Days[i]);
                            }
                            break;
                    }
                }
            }
            catch
            {
                // Битый или недоступный конфиг не должен мешать запуску —
                // молча работаем на значениях по умолчанию.
            }
            return c;
        }

        public void Save()
        {
            Directory.CreateDirectory(Dir);

            StringBuilder sb = new StringBuilder();
            sb.AppendLine("# VPN Connect Monitoring — настройки");
            sb.AppendLine("# Изменения проще делать через окно настроек приложения.");
            sb.AppendLine();
            sb.AppendLine("VpnName=" + VpnName);
            sb.AppendLine("Enabled=" + (Enabled ? "1" : "0"));
            sb.AppendLine("IntervalSeconds=" + IntervalSeconds.ToString(CultureInfo.InvariantCulture));
            sb.AppendLine("WorkStartMinutes=" + WorkStartMinutes.ToString(CultureInfo.InvariantCulture));
            sb.AppendLine("WorkEndMinutes=" + WorkEndMinutes.ToString(CultureInfo.InvariantCulture));
            sb.AppendLine("RepeatSuppressMinutes=" + RepeatSuppressMinutes.ToString(CultureInfo.InvariantCulture));
            sb.AppendLine("NotifyOnRestore=" + (NotifyOnRestore ? "1" : "0"));
            sb.AppendLine("SoundEnabled=" + (SoundEnabled ? "1" : "0"));

            StringBuilder days = new StringBuilder();
            for (int i = 0; i < 7; i++)
            {
                if (i > 0) days.Append(',');
                days.Append(Days[i] ? "1" : "0");
            }
            sb.AppendLine("Days=" + days);

            File.WriteAllText(FilePath, sb.ToString(), new UTF8Encoding(true));
        }

        static bool ParseBool(string v, bool fallback)
        {
            if (string.IsNullOrEmpty(v)) return fallback;
            v = v.ToLowerInvariant();
            if (v == "1" || v == "true" || v == "yes" || v == "да") return true;
            if (v == "0" || v == "false" || v == "no" || v == "нет") return false;
            return fallback;
        }

        static int ParseInt(string v, int fallback, int min, int max)
        {
            int result;
            if (!int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out result))
                return fallback;
            if (result < min) result = min;
            if (result > max) result = max;
            return result;
        }
    }
}
