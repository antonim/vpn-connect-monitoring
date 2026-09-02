using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Windows.Forms;

namespace VpnConnectMonitoring
{
    // Временная обвязка для проверки вёрстки: показывает окно за пределами
    // экрана и сохраняет его отрисовку в PNG. В состав продукта не входит —
    // собирается скриптом tools\render-settings.ps1.
    static class ShotProgram
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string which = args.Length > 0 ? args[0] : "settings";
            string outPath = args.Length > 1 ? args[1] : which + ".png";

            Form f = which == "history"
                ? (Form)new HistoryForm()
                : new SettingsForm(Config.Load());

            f.StartPosition = FormStartPosition.Manual;
            f.Location = new Point(-4000, -4000);
            f.Show();
            Application.DoEvents();

            using (Bitmap bmp = new Bitmap(f.Width, f.Height))
            {
                f.DrawToBitmap(bmp, new Rectangle(0, 0, f.Width, f.Height));
                bmp.Save(outPath, ImageFormat.Png);
            }

            f.Close();
        }
    }
}
