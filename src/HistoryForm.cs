using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.IO;
using System.Windows.Forms;

namespace VpnConnectMonitoring
{
    public class HistoryForm : Form
    {
        static readonly int[] RangeHours = { 24, 72, 168, 720 };
        static readonly string[] RangeNames = { "24 часа", "3 дня", "7 дней", "30 дней" };

        ComboBox cbRange;
        TimelinePanel timeline;
        Label lblHover;
        Label lblStats;
        ListView lvOutages;
        Timer autoRefresh;

        public HistoryForm()
        {
            BuildUi();
            Reload();
        }

        void BuildUi()
        {
            Text = "VPN Connect Monitoring — журнал подключения";
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(820, 600);
            MinimumSize = new Size(700, 500);
            Font = new Font("Segoe UI", 9f);

            Label lblRange = new Label();
            lblRange.Text = "Период:";
            lblRange.SetBounds(12, 15, 60, 20);
            Controls.Add(lblRange);

            cbRange = new ComboBox();
            cbRange.DropDownStyle = ComboBoxStyle.DropDownList;
            cbRange.SetBounds(72, 11, 120, 24);
            for (int i = 0; i < RangeNames.Length; i++)
                cbRange.Items.Add(RangeNames[i]);
            cbRange.SelectedIndex = 0;
            cbRange.SelectedIndexChanged += delegate { Reload(); };
            Controls.Add(cbRange);

            Button btnRefresh = new Button();
            btnRefresh.Text = "Обновить";
            btnRefresh.SetBounds(202, 10, 90, 26);
            btnRefresh.Click += delegate { Reload(); };
            Controls.Add(btnRefresh);

            Button btnOpen = new Button();
            btnOpen.Text = "Открыть файл журнала";
            btnOpen.SetBounds(300, 10, 160, 26);
            btnOpen.Click += BtnOpen_Click;
            Controls.Add(btnOpen);

            timeline = new TimelinePanel();
            timeline.SetBounds(12, 46, ClientSize.Width - 24, 96);
            timeline.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            timeline.Hover += Timeline_Hover;
            Controls.Add(timeline);

            lblHover = new Label();
            lblHover.SetBounds(12, 146, ClientSize.Width - 24, 20);
            lblHover.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            lblHover.ForeColor = Color.FromArgb(90, 96, 106);
            lblHover.Text = "Наведите курсор на ленту, чтобы увидеть состояние в конкретный момент.";
            Controls.Add(lblHover);

            // Легенда
            Panel legend = new Panel();
            legend.SetBounds(12, 170, ClientSize.Width - 24, 24);
            legend.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            Controls.Add(legend);
            AddLegendItem(legend, 0, Icons.Ok, "подключено");
            AddLegendItem(legend, 150, Icons.Alarm, "нет связи");
            AddLegendItem(legend, 280, Icons.IdleBand, "не наблюдалось");

            lblStats = new Label();
            lblStats.SetBounds(12, 200, ClientSize.Width - 24, 44);
            lblStats.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            Controls.Add(lblStats);

            Label lblList = new Label();
            lblList.Text = "Обрывы связи:";
            lblList.SetBounds(12, 250, 200, 20);
            Controls.Add(lblList);

            lvOutages = new ListView();
            lvOutages.View = View.Details;
            lvOutages.FullRowSelect = true;
            lvOutages.GridLines = true;
            lvOutages.SetBounds(12, 272, ClientSize.Width - 24, ClientSize.Height - 284);
            lvOutages.Anchor = AnchorStyles.Top | AnchorStyles.Left
                             | AnchorStyles.Right | AnchorStyles.Bottom;
            lvOutages.Columns.Add("Начало", 190);
            lvOutages.Columns.Add("Окончание", 190);
            lvOutages.Columns.Add("Длительность", 140);
            lvOutages.Columns.Add("Примечание", 250);
            Controls.Add(lvOutages);

            // Журнал пополняется фоном, поэтому окно освежаем само.
            autoRefresh = new Timer();
            autoRefresh.Interval = 30000;
            autoRefresh.Tick += delegate { Reload(); };
            autoRefresh.Start();

            FormClosed += delegate { autoRefresh.Stop(); };
        }

        static void AddLegendItem(Panel host, int x, Color color, string text)
        {
            Panel swatch = new Panel();
            swatch.BackColor = color;
            swatch.SetBounds(x, 4, 14, 14);
            host.Controls.Add(swatch);

            Label lbl = new Label();
            lbl.Text = text;
            lbl.SetBounds(x + 20, 2, 130, 20);
            host.Controls.Add(lbl);
        }

        void BtnOpen_Click(object sender, EventArgs e)
        {
            try
            {
                if (!File.Exists(History.FilePath))
                {
                    MessageBox.Show(this, "Файл журнала ещё не создан.",
                        Notifier.DisplayName, MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return;
                }
                Process.Start("notepad.exe", History.FilePath);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Не удалось открыть журнал:\n" + ex.Message,
                    Notifier.DisplayName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        void Timeline_Hover(DateTime time, VpnState state)
        {
            if (time == DateTime.MinValue)
            {
                lblHover.Text = "Наведите курсор на ленту, чтобы увидеть состояние в конкретный момент.";
                return;
            }

            lblHover.Text = time.ToString("dd.MM.yyyy HH:mm", CultureInfo.CurrentCulture)
                + "  —  " + StateName(state);
        }

        static string StateName(VpnState s)
        {
            if (s == VpnState.Up) return "подключено";
            if (s == VpnState.Down) return "нет связи";
            return "не наблюдалось";
        }

        void Reload()
        {
            DateTime to = DateTime.Now;
            DateTime from = to.AddHours(-RangeHours[cbRange.SelectedIndex]);

            List<HistorySample> samples = History.Load(from);
            List<Segment> segments = History.BuildSegments(samples, from, to);

            timeline.SetData(segments, from, to);

            TimeSpan up = TimeSpan.Zero, down = TimeSpan.Zero, idle = TimeSpan.Zero;
            TimeSpan longest = TimeSpan.Zero;

            lvOutages.BeginUpdate();
            lvOutages.Items.Clear();

            for (int i = 0; i < segments.Count; i++)
            {
                Segment s = segments[i];
                if (s.State == VpnState.Up) up += s.Duration;
                else if (s.State == VpnState.Down) down += s.Duration;
                else idle += s.Duration;

                if (s.State != VpnState.Down)
                    continue;

                if (s.Duration > longest)
                    longest = s.Duration;

                bool ongoing = i == segments.Count - 1;
                ListViewItem item = new ListViewItem(s.Start.ToString("dd.MM.yyyy HH:mm:ss"));
                item.SubItems.Add(ongoing ? "продолжается" : s.End.ToString("dd.MM.yyyy HH:mm:ss"));
                item.SubItems.Add(FormatDuration(s.Duration));
                item.SubItems.Add(ongoing ? "связи нет прямо сейчас" : "");
                item.ForeColor = Icons.Alarm;
                lvOutages.Items.Add(item);
            }

            // Свежие обрывы интереснее старых.
            lvOutages.Sorting = SortOrder.None;
            List<ListViewItem> reversed = new List<ListViewItem>();
            for (int i = lvOutages.Items.Count - 1; i >= 0; i--)
                reversed.Add(lvOutages.Items[i]);
            lvOutages.Items.Clear();
            lvOutages.Items.AddRange(reversed.ToArray());
            lvOutages.EndUpdate();

            TimeSpan observed = up + down;
            string availability = observed.TotalSeconds > 0
                ? (up.TotalSeconds / observed.TotalSeconds * 100.0).ToString("0.0", CultureInfo.CurrentCulture) + " %"
                : "нет данных";

            lblStats.Text =
                "Доступность за период: " + availability
                    + "     Обрывов: " + lvOutages.Items.Count
                    + "     Суммарно без связи: " + FormatDuration(down)
                    + "     Самый долгий: " + FormatDuration(longest)
                + Environment.NewLine
                + "Под наблюдением: " + FormatDuration(observed)
                    + "     Не наблюдалось: " + FormatDuration(idle)
                    + "  (программа не работала, пауза, вне расписания)";
        }

        public static string FormatDuration(TimeSpan t)
        {
            if (t.TotalSeconds < 1)
                return "—";
            if (t.TotalMinutes < 1)
                return ((int)t.TotalSeconds) + " сек";
            if (t.TotalHours < 1)
                return ((int)t.TotalMinutes) + " мин";
            if (t.TotalDays < 1)
                return ((int)t.TotalHours) + " ч " + t.Minutes + " мин";
            return ((int)t.TotalDays) + " д " + t.Hours + " ч " + t.Minutes + " мин";
        }

        // --- Лента состояний ------------------------------------------------

        class TimelinePanel : Control
        {
            const int PadLeft = 8;
            const int PadRight = 8;
            const int BandTop = 10;
            const int BandHeight = 46;

            List<Segment> segments = new List<Segment>();
            DateTime from = DateTime.Now.AddHours(-24);
            DateTime to = DateTime.Now;

            public event Action<DateTime, VpnState> Hover;

            public TimelinePanel()
            {
                SetStyle(ControlStyles.OptimizedDoubleBuffer
                       | ControlStyles.AllPaintingInWmPaint
                       | ControlStyles.UserPaint
                       | ControlStyles.ResizeRedraw, true);
            }

            public void SetData(List<Segment> data, DateTime rangeFrom, DateTime rangeTo)
            {
                segments = data;
                from = rangeFrom;
                to = rangeTo;
                Invalidate();
            }

            int BandWidth
            {
                get { return Math.Max(1, Width - PadLeft - PadRight); }
            }

            double TotalSeconds
            {
                get { return Math.Max(1.0, (to - from).TotalSeconds); }
            }

            int TimeToX(DateTime t)
            {
                double frac = (t - from).TotalSeconds / TotalSeconds;
                if (frac < 0) frac = 0;
                if (frac > 1) frac = 1;
                return PadLeft + (int)Math.Round(frac * BandWidth);
            }

            DateTime XToTime(int x)
            {
                double frac = (double)(x - PadLeft) / BandWidth;
                if (frac < 0) frac = 0;
                if (frac > 1) frac = 1;
                return from.AddSeconds(frac * TotalSeconds);
            }

            static Color ColorOf(VpnState s)
            {
                if (s == VpnState.Up) return Icons.Ok;
                if (s == VpnState.Down) return Icons.Alarm;
                return Icons.IdleBand;
            }

            protected override void OnPaint(PaintEventArgs e)
            {
                Graphics g = e.Graphics;
                g.Clear(BackColor);
                g.SmoothingMode = SmoothingMode.None;

                for (int i = 0; i < segments.Count; i++)
                {
                    Segment s = segments[i];
                    int x1 = TimeToX(s.Start);
                    int x2 = TimeToX(s.End);
                    int w = x2 - x1;

                    // Короткий обрыв на длинном диапазоне занимает доли пикселя.
                    // Такие случаи важнее всего, поэтому даём им минимум 2 px —
                    // иначе на месяце минутный обрыв просто исчезнет с графика.
                    if (s.State == VpnState.Down && w < 2)
                        w = 2;
                    if (w < 1)
                        w = 1;

                    using (SolidBrush b = new SolidBrush(ColorOf(s.State)))
                        g.FillRectangle(b, x1, BandTop, w, BandHeight);
                }

                using (Pen p = new Pen(Color.FromArgb(150, 156, 166)))
                    g.DrawRectangle(p, PadLeft, BandTop, BandWidth, BandHeight);

                DrawAxis(g);
            }

            void DrawAxis(Graphics g)
            {
                double spanHours = (to - from).TotalHours;
                int[] steps = { 1, 2, 3, 6, 12, 24, 48, 72, 120, 168 };
                int stepHours = steps[steps.Length - 1];
                for (int i = 0; i < steps.Length; i++)
                {
                    if (spanHours / steps[i] <= 10)
                    {
                        stepHours = steps[i];
                        break;
                    }
                }

                bool dayLabels = stepHours >= 24;

                // Первая засечка — ближайшая «круглая» граница после начала.
                DateTime tick = new DateTime(from.Year, from.Month, from.Day, from.Hour, 0, 0);
                while (tick.Hour % stepHours != 0 || tick < from)
                    tick = tick.AddHours(1);

                int axisY = BandTop + BandHeight;
                using (Pen p = new Pen(Color.FromArgb(190, 195, 203)))
                using (SolidBrush b = new SolidBrush(Color.FromArgb(90, 96, 106)))
                using (Font f = new Font("Segoe UI", 8f))
                using (StringFormat sf = new StringFormat())
                {
                    sf.Alignment = StringAlignment.Center;

                    while (tick <= to)
                    {
                        int x = TimeToX(tick);
                        g.DrawLine(p, x, axisY, x, axisY + 4);

                        string label = dayLabels
                            ? tick.ToString("dd.MM")
                            : tick.ToString("HH:mm");

                        g.DrawString(label, f, b, x, axisY + 6, sf);
                        tick = tick.AddHours(stepHours);
                    }
                }
            }

            protected override void OnMouseMove(MouseEventArgs e)
            {
                base.OnMouseMove(e);
                if (Hover == null)
                    return;

                if (e.Y < BandTop || e.Y > BandTop + BandHeight
                    || e.X < PadLeft || e.X > PadLeft + BandWidth)
                {
                    Hover(DateTime.MinValue, VpnState.Unknown);
                    return;
                }

                DateTime t = XToTime(e.X);
                VpnState state = VpnState.Unknown;
                for (int i = 0; i < segments.Count; i++)
                {
                    if (t >= segments[i].Start && t < segments[i].End)
                    {
                        state = segments[i].State;
                        break;
                    }
                }
                Hover(t, state);
            }

            protected override void OnMouseLeave(EventArgs e)
            {
                base.OnMouseLeave(e);
                if (Hover != null)
                    Hover(DateTime.MinValue, VpnState.Unknown);
            }
        }
    }
}
