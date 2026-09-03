using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using Microsoft.Win32;

namespace VpnConnectMonitoring
{
    // Установка целиком в пользовательский профиль: ни один шаг не требует
    // прав администратора, поэтому коллеге достаточно запустить один файл.
    public static class Installer
    {
        public const string AppName = "VpnConnectMonitoring";
        const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        const string RunValue = "VpnConnectMonitoring";

        // Задача из первой версии решения. Если её не снять, уведомления будут
        // приходить дважды — из планировщика и из трея.
        public const string LegacyTaskName = "AVIA VPN Watchdog";

        public static string InstallDir
        {
            get
            {
                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Programs", AppName);
            }
        }

        public static string TargetExe
        {
            get { return Path.Combine(InstallDir, "VpnConnectMonitoring.exe"); }
        }

        public static string CurrentExe
        {
            get { return Assembly.GetExecutingAssembly().Location; }
        }

        public static bool IsInstalled
        {
            get { return File.Exists(TargetExe); }
        }

        public static bool IsRunningFromInstallDir
        {
            get
            {
                try
                {
                    return string.Equals(
                        Path.GetFullPath(CurrentExe),
                        Path.GetFullPath(TargetExe),
                        StringComparison.OrdinalIgnoreCase);
                }
                catch
                {
                    return false;
                }
            }
        }

        public static bool AutostartEnabled
        {
            get
            {
                try
                {
                    using (RegistryKey k = Registry.CurrentUser.OpenSubKey(RunKey, false))
                    {
                        if (k != null && k.GetValue(RunValue) != null)
                            return true;
                    }
                }
                catch { }

                return Shortcut.StartupEnabled;
            }
        }

        // Автозапуск прописывается сразу двумя способами: ключом Run и ярлыком
        // в папке «Автозагрузка». Это не перестраховка ради перестраховки —
        // исправная запись в Run однажды не отработала при входе в систему,
        // причину выяснить не удалось. Механизмы независимы, а дубль запуска
        // безвреден: второй экземпляр с --tray завершается молча.
        public static void SetAutostart(bool enabled, string exePath)
        {
            using (RegistryKey k = Registry.CurrentUser.CreateSubKey(RunKey))
            {
                if (k != null)
                {
                    if (enabled)
                        k.SetValue(RunValue, "\"" + exePath + "\" --tray");
                    else if (k.GetValue(RunValue) != null)
                        k.DeleteValue(RunValue, false);
                }
            }

            if (enabled)
                Shortcut.EnsureStartup(exePath);
            else
                Shortcut.RemoveStartup();
        }

        // Копирует себя в профиль и включает автозапуск. Возвращает путь
        // установленного файла. Если приложение уже запущено из целевой папки,
        // копирование пропускается.
        public static string Install()
        {
            Directory.CreateDirectory(InstallDir);

            if (!IsRunningFromInstallDir)
                File.Copy(CurrentExe, TargetExe, true);

            SetAutostart(true, TargetExe);
            return TargetExe;
        }

        public static void Uninstall(bool removeSettings)
        {
            SetAutostart(false, TargetExe);
            Shortcut.Remove();

            if (removeSettings)
            {
                try
                {
                    if (Directory.Exists(Config.Dir))
                        Directory.Delete(Config.Dir, true);
                }
                catch { }
            }

            // Работающий exe удалить нельзя, поэтому уборку папки поручаем
            // отдельному процессу, который стартует после нашего выхода.
            try
            {
                if (!Directory.Exists(InstallDir))
                    return;

                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "cmd.exe";
                psi.Arguments = "/c ping 127.0.0.1 -n 4 >nul & rd /s /q \"" + InstallDir + "\"";
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                Process.Start(psi);
            }
            catch { }
        }

        public static bool LegacyTaskExists()
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "schtasks.exe";
                psi.Arguments = "/Query /TN \"" + LegacyTaskName + "\"";
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;

                using (Process p = Process.Start(psi))
                {
                    p.StandardOutput.ReadToEnd();
                    p.StandardError.ReadToEnd();
                    p.WaitForExit(5000);
                    return p.HasExited && p.ExitCode == 0;
                }
            }
            catch
            {
                return false;
            }
        }

        public static bool RemoveLegacyTask()
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "schtasks.exe";
                psi.Arguments = "/Delete /TN \"" + LegacyTaskName + "\" /F";
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;

                using (Process p = Process.Start(psi))
                {
                    p.StandardOutput.ReadToEnd();
                    p.StandardError.ReadToEnd();
                    p.WaitForExit(5000);
                    return p.HasExited && p.ExitCode == 0;
                }
            }
            catch
            {
                return false;
            }
        }
    }
}
