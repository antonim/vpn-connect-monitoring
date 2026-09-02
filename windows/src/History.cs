using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace VpnConnectMonitoring
{
    public enum VpnState
    {
        Unknown = 0,   // наблюдение не велось: программа не работала, пауза,
                       // вне расписания или выключено
        Up = 1,
        Down = 2
    }

    public class HistorySample
    {
        public DateTime Time;
        public VpnState State;
    }

    public class Segment
    {
        public DateTime Start;
        public DateTime End;
        public VpnState State;

        public TimeSpan Duration
        {
            get { return End - Start; }
        }
    }

    // Журнал состояний в %APPDATA%\VpnConnectMonitoring\history.csv.
    //
    // Пишем не каждую проверку, а смену состояния плюс «сердцебиение» раз в
    // HeartbeatMinutes. Это держит файл компактным и одновременно позволяет
    // отличить «связь была всё время» от «программа не работала»: разрыв между
    // соседними записями больше GapMinutes означает, что наблюдения не было —
    // так корректно отображаются выключение компьютера, сон и аварийное
    // завершение, после которых закрывающей записи не остаётся.
    public static class History
    {
        public const int HeartbeatMinutes = 5;
        public const int GapMinutes = 12;
        public const int RetentionDays = 30;

        const string TimeFormat = "yyyy-MM-dd HH:mm:ss";

        static DateTime lastWrite = DateTime.MinValue;
        static VpnState lastState = VpnState.Unknown;
        static readonly object gate = new object();

        public static string FilePath
        {
            get { return Path.Combine(Config.Dir, "history.csv"); }
        }

        public static void Record(DateTime now, VpnState state)
        {
            lock (gate)
            {
                bool sameState = state == lastState && lastWrite != DateTime.MinValue;
                if (sameState && (now - lastWrite).TotalMinutes < HeartbeatMinutes)
                    return;

                try
                {
                    Directory.CreateDirectory(Config.Dir);
                    File.AppendAllText(FilePath,
                        now.ToString(TimeFormat, CultureInfo.InvariantCulture)
                            + ";" + Code(state) + Environment.NewLine,
                        Encoding.UTF8);

                    lastWrite = now;
                    lastState = state;
                }
                catch
                {
                    // Журнал — вспомогательная функция; сбой записи не должен
                    // ломать основную работу наблюдателя.
                }
            }
        }

        static string Code(VpnState s)
        {
            if (s == VpnState.Up) return "up";
            if (s == VpnState.Down) return "down";
            return "idle";
        }

        static VpnState Parse(string s)
        {
            if (s == "up") return VpnState.Up;
            if (s == "down") return VpnState.Down;
            return VpnState.Unknown;
        }

        // Возвращает записи начиная с from, плюс последнюю запись перед from —
        // без неё неизвестно состояние на левой границе диапазона.
        public static List<HistorySample> Load(DateTime from)
        {
            List<HistorySample> result = new List<HistorySample>();
            HistorySample before = null;

            try
            {
                if (!File.Exists(FilePath))
                    return result;

                foreach (string raw in File.ReadAllLines(FilePath, Encoding.UTF8))
                {
                    string line = raw.Trim();
                    if (line.Length == 0)
                        continue;

                    int sep = line.IndexOf(';');
                    if (sep <= 0)
                        continue;

                    DateTime t;
                    if (!DateTime.TryParseExact(line.Substring(0, sep), TimeFormat,
                            CultureInfo.InvariantCulture, DateTimeStyles.None, out t))
                        continue;

                    HistorySample s = new HistorySample();
                    s.Time = t;
                    s.State = Parse(line.Substring(sep + 1).Trim().ToLowerInvariant());

                    if (t < from)
                        before = s;
                    else
                        result.Add(s);
                }
            }
            catch
            {
                return result;
            }

            if (before != null)
                result.Insert(0, before);

            return result;
        }

        public static void Prune()
        {
            try
            {
                if (!File.Exists(FilePath))
                    return;

                DateTime cutoff = DateTime.Now.Date.AddDays(-RetentionDays);
                string[] lines = File.ReadAllLines(FilePath, Encoding.UTF8);

                List<string> keep = new List<string>();
                for (int i = 0; i < lines.Length; i++)
                {
                    string line = lines[i].Trim();
                    if (line.Length == 0)
                        continue;

                    int sep = line.IndexOf(';');
                    DateTime t;
                    if (sep > 0 && DateTime.TryParseExact(line.Substring(0, sep), TimeFormat,
                            CultureInfo.InvariantCulture, DateTimeStyles.None, out t)
                        && t < cutoff)
                    {
                        continue;
                    }
                    keep.Add(line);
                }

                if (keep.Count != lines.Length)
                    File.WriteAllLines(FilePath, keep.ToArray(), Encoding.UTF8);
            }
            catch { }
        }

        // Разворачивает точечные записи в непрерывную ленту отрезков,
        // покрывающую весь диапазон [from, to] без пропусков.
        public static List<Segment> BuildSegments(List<HistorySample> samples,
            DateTime from, DateTime to)
        {
            List<Segment> raw = new List<Segment>();

            if (samples == null || samples.Count == 0)
            {
                Add(raw, from, to, VpnState.Unknown);
                return Merge(raw);
            }

            DateTime cursor = from;

            for (int i = 0; i < samples.Count; i++)
            {
                DateTime sStart = samples[i].Time;
                DateTime sEnd = (i + 1 < samples.Count) ? samples[i + 1].Time : to;
                if (sEnd > to) sEnd = to;

                // Запись подтверждает состояние лишь на ближайшие GapMinutes;
                // дальше — только если пришла следующая запись.
                DateTime confirmedUntil = sStart.AddMinutes(GapMinutes);
                DateTime knownEnd = sEnd < confirmedUntil ? sEnd : confirmedUntil;

                DateTime a = Max(sStart, cursor);
                if (a > cursor)
                    Add(raw, cursor, a, VpnState.Unknown);

                Add(raw, a, Max(a, Min(knownEnd, to)), samples[i].State);

                if (knownEnd < sEnd)
                    Add(raw, Max(knownEnd, from), Min(sEnd, to), VpnState.Unknown);

                cursor = Max(cursor, Min(sEnd, to));
            }

            if (cursor < to)
                Add(raw, cursor, to, VpnState.Unknown);

            return Merge(raw);
        }

        static void Add(List<Segment> list, DateTime start, DateTime end, VpnState state)
        {
            if (end <= start)
                return;

            Segment s = new Segment();
            s.Start = start;
            s.End = end;
            s.State = state;
            list.Add(s);
        }

        static List<Segment> Merge(List<Segment> input)
        {
            List<Segment> result = new List<Segment>();
            for (int i = 0; i < input.Count; i++)
            {
                if (result.Count > 0)
                {
                    Segment last = result[result.Count - 1];
                    if (last.State == input[i].State && last.End >= input[i].Start)
                    {
                        if (input[i].End > last.End)
                            last.End = input[i].End;
                        continue;
                    }
                }
                result.Add(input[i]);
            }
            return result;
        }

        static DateTime Min(DateTime a, DateTime b) { return a < b ? a : b; }
        static DateTime Max(DateTime a, DateTime b) { return a > b ? a : b; }
    }
}
