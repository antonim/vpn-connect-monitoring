using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

namespace VpnConnectMonitoring
{
    // Значки рисуются в рантайме, чтобы приложение оставалось одним файлом
    // без внешних ресурсов. Создаются один раз при старте и живут до выхода.
    public static class Icons
    {
        [DllImport("user32.dll", SetLastError = true)]
        static extern bool DestroyIcon(IntPtr handle);

        public static readonly Color Ok = Color.FromArgb(46, 160, 67);
        public static readonly Color Alarm = Color.FromArgb(218, 54, 51);
        public static readonly Color Idle = Color.FromArgb(125, 133, 144);

        // Тот же смысл, что и Idle, но для крупных заливок на графике:
        // насыщенный серый там спорит с красным и зелёным за внимание.
        public static readonly Color IdleBand = Color.FromArgb(210, 214, 220);

        public enum Glyph
        {
            Check,   // связь есть
            Bang,    // связи нет
            Dash     // не наблюдается
        }

        // Состояние различается и цветом, и формой. Только цвета мало: значок
        // в трее отрисовывается примерно в 16 пикселей, а красный и зелёный
        // одинаковой яркости неразличимы при дальтонизме.
        //
        // Надписи здесь принципиально нет: «VPN» шрифтом, читаемым на 16 px,
        // в кружок не влезает и переносится на две строки.
        public static Icon Create(Color fill, Glyph glyph)
        {
            using (Bitmap bmp = new Bitmap(32, 32))
            {
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    g.Clear(Color.Transparent);

                    using (SolidBrush b = new SolidBrush(fill))
                        g.FillEllipse(b, 1, 1, 30, 30);

                    using (Pen p = new Pen(Color.FromArgb(70, 0, 0, 0), 1.5f))
                        g.DrawEllipse(p, 1.5f, 1.5f, 29, 29);

                    DrawGlyph(g, glyph);
                }

                IntPtr h = bmp.GetHicon();
                try
                {
                    // Клонируем, чтобы не зависеть от времени жизни HICON,
                    // и сразу освобождаем дескриптор.
                    using (Icon tmp = Icon.FromHandle(h))
                        return (Icon)tmp.Clone();
                }
                finally
                {
                    DestroyIcon(h);
                }
            }
        }

        static void DrawGlyph(Graphics g, Glyph glyph)
        {
            using (Pen pen = new Pen(Color.White, 4f))
            {
                pen.StartCap = LineCap.Round;
                pen.EndCap = LineCap.Round;
                pen.LineJoin = LineJoin.Round;

                switch (glyph)
                {
                    case Glyph.Check:
                        g.DrawLines(pen, new PointF[] {
                            new PointF(9f, 16.5f),
                            new PointF(14f, 21.5f),
                            new PointF(23f, 11f),
                        });
                        break;

                    case Glyph.Bang:
                        g.DrawLine(pen, 16f, 8.5f, 16f, 18f);
                        // Точку рисуем заливкой: круглый колпачок линии
                        // нулевой длины отрисовывается не везде одинаково.
                        g.FillEllipse(Brushes.White, 13.75f, 21f, 4.5f, 4.5f);
                        break;

                    case Glyph.Dash:
                        g.DrawLine(pen, 10f, 16f, 22f, 16f);
                        break;
                }
            }
        }
    }
}
