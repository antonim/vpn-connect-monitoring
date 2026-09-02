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

        public static Icon Create(Color fill)
        {
            using (Bitmap bmp = new Bitmap(32, 32))
            {
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAlias;
                    g.Clear(Color.Transparent);

                    using (SolidBrush b = new SolidBrush(fill))
                        g.FillEllipse(b, 1, 1, 30, 30);

                    using (Pen p = new Pen(Color.FromArgb(70, 0, 0, 0), 2f))
                        g.DrawEllipse(p, 2, 2, 28, 28);

                    using (Font f = new Font("Segoe UI", 15f, FontStyle.Bold, GraphicsUnit.Pixel))
                    using (StringFormat sf = new StringFormat())
                    {
                        sf.Alignment = StringAlignment.Center;
                        sf.LineAlignment = StringAlignment.Center;
                        g.DrawString("VPN", f, Brushes.White, new RectangleF(0, 1, 32, 32), sf);
                    }
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
    }
}
