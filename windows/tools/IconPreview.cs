using System;
using System.Drawing;
using System.Drawing.Imaging;

namespace VpnConnectMonitoring
{
    // Раскладывает значки трея в один PNG для визуальной проверки: слева
    // в натуральную величину 32 px, справа — 16 px, как их реально рисует
    // панель задач, с увеличением для разглядывания.
    // В состав продукта не входит, собирается tools\render-icons.ps1.
    static class IconPreviewProgram
    {
        [STAThread]
        static void Main(string[] args)
        {
            string outPath = args.Length > 0 ? args[0] : "icons.png";

            var items = new[]
            {
                new { Color = Icons.Ok, Glyph = Icons.Glyph.Check, Name = "связь есть" },
                new { Color = Icons.Alarm, Glyph = Icons.Glyph.Bang, Name = "связи нет" },
                new { Color = Icons.Idle, Glyph = Icons.Glyph.Dash, Name = "не наблюдается" },
            };

            using (Bitmap sheet = new Bitmap(430, 150))
            using (Graphics g = Graphics.FromImage(sheet))
            {
                g.Clear(Color.White);
                g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.Half;

                using (Font caption = new Font("Segoe UI", 9f))
                {
                    g.DrawString("32 px", caption, Brushes.Gray, 20, 8);
                    g.DrawString("16 px", caption, Brushes.Gray, 90, 8);
                    g.DrawString("16 px, увеличено ×4", caption, Brushes.Gray, 160, 8);

                    int y = 30;
                    foreach (var item in items)
                    {
                        using (Icon icon = Icons.Create(item.Color, item.Glyph))
                        using (Bitmap big = icon.ToBitmap())
                        using (Bitmap small = new Bitmap(big, new Size(16, 16)))
                        {
                            g.DrawImage(big, 20, y);
                            g.DrawImage(small, 95, y + 8);
                            g.DrawImage(small, new Rectangle(160, y - 8, 64, 64));
                            g.DrawString(item.Name, caption, Brushes.Black, 240, y + 12);
                        }
                        y += 40;
                    }
                }

                sheet.Save(outPath, ImageFormat.Png);
            }
        }
    }
}
