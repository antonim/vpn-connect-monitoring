using System;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

namespace VpnConnectMonitoring
{
    // Уведомления идут через WinRT с собственным AppUserModelID.
    //
    // Ключевой момент: с НЕзарегистрированным AppID вызов Show() завершается
    // успешно и не бросает исключений, но система молча выбрасывает
    // уведомление — оно не появляется ни баннером, ни в центре уведомлений.
    // Поэтому EnsureRegistered() обязан отработать до первого показа.
    //
    // Воздушная подсказка NotifyIcon оставлена запасным путём: на части
    // конфигураций автоматически сгенерированный AUMID не срабатывает.
    public static class Notifier
    {
        public const string AppId = "VpnConnectMonitoring";
        public const string DisplayName = "VPN Connect Monitoring";

        const string AppIdKey = @"SOFTWARE\Classes\AppUserModelId\" + AppId;

        static Type typeManager;
        static Type typeXml;
        static Type typeToast;
        static bool typesResolved;

        [DllImport("shell32.dll", SetLastError = true)]
        static extern int SetCurrentProcessExplicitAppUserModelID(
            [MarshalAs(UnmanagedType.LPWStr)] string AppID);

        public static void EnsureRegistered()
        {
            try
            {
                using (RegistryKey k = Registry.CurrentUser.CreateSubKey(AppIdKey))
                {
                    if (k == null)
                    {
                        Log.Write("EnsureRegistered: не удалось открыть ключ реестра");
                        return;
                    }
                    k.SetValue("DisplayName", DisplayName, RegistryValueKind.String);
                    k.SetValue("ShowInSettings", 1, RegistryValueKind.DWord);
                }

                // Процесс должен объявить тот же AppUserModelID, иначе система
                // связывает уведомление с другим источником.
                int hr = SetCurrentProcessExplicitAppUserModelID(AppId);
                Log.Write("EnsureRegistered: AppId=" + AppId
                    + " зарегистрирован, SetCurrentProcessExplicitAppUserModelID -> 0x"
                    + hr.ToString("X8"));
            }
            catch (Exception ex)
            {
                Log.Write("EnsureRegistered: ИСКЛЮЧЕНИЕ " + ex.Message);
            }
        }

        public static void Unregister()
        {
            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(AppIdKey, false);
            }
            catch { }
        }

        // Показывает уведомление. Если WinRT недоступен, возвращает false —
        // вызывающий код показывает воздушную подсказку.
        public static bool TryShow(string title, string text)
        {
            if (!ResolveTypes())
            {
                Log.Write("TryShow: типы WinRT не разрешились -> откат на NotifyIcon");
                return false;
            }

            try
            {
                object xml = Activator.CreateInstance(typeXml);
                MethodInfo load = typeXml.GetMethod("LoadXml", new Type[] { typeof(string) });
                if (load == null)
                    return false;
                load.Invoke(xml, new object[] { BuildXml(title, text) });

                object toast = Activator.CreateInstance(typeToast, new object[] { xml });

                MethodInfo create = typeManager.GetMethod(
                    "CreateToastNotifier", new Type[] { typeof(string) });
                if (create == null)
                    return false;

                object notifier = create.Invoke(null, new object[] { AppId });
                MethodInfo show = notifier.GetType().GetMethod("Show");
                if (show == null)
                    return false;

                // Setting сообщает, что платформа думает о нашем AppID:
                // Enabled / DisabledForApplication / DisabledByGroupPolicy и т. п.
                string setting = "?";
                try
                {
                    PropertyInfo pi = notifier.GetType().GetProperty("Setting");
                    if (pi != null)
                    {
                        object v = pi.GetValue(notifier, null);
                        if (v != null) setting = v.ToString();
                    }
                }
                catch { }

                show.Invoke(notifier, new object[] { toast });
                Log.Write("TryShow: WinRT Show() выполнен, AppId=" + AppId
                    + ", NotificationSetting=" + setting + ", заголовок=\"" + title + "\"");
                return true;
            }
            catch (Exception ex)
            {
                Exception e = ex is TargetInvocationException && ex.InnerException != null
                    ? ex.InnerException : ex;
                Log.Write("TryShow: ИСКЛЮЧЕНИЕ " + e.GetType().Name + ": " + e.Message);
                return false;
            }
        }

        static string BuildXml(string title, string text)
        {
            // duration="long" держит баннер на экране около 25 секунд вместо
            // пяти. Обрыв VPN легко пропустить за пять секунд — именно это и
            // произошло при первом реальном срабатывании.
            //
            // Звук у самого уведомления выключен: своим сигналом из Sound
            // управлять проще, и он не сливается со звуками остальных
            // приложений.
            return "<toast duration=\"long\">"
                 + "<visual><binding template=\"ToastGeneric\">"
                 + "<text>" + Escape(title) + "</text>"
                 + "<text>" + Escape(text) + "</text>"
                 + "</binding></visual>"
                 + "<audio silent=\"true\"/>"
                 + "</toast>";
        }

        static string Escape(string s)
        {
            if (string.IsNullOrEmpty(s))
                return string.Empty;
            return s.Replace("&", "&amp;")
                    .Replace("<", "&lt;")
                    .Replace(">", "&gt;")
                    .Replace("\"", "&quot;");
        }

        // Типы WinRT грузим рефлексией: ссылку на Windows.winmd во время
        // компиляции дать нечем — Windows SDK для сборки не требуется.
        static bool ResolveTypes()
        {
            if (typesResolved)
                return typeManager != null && typeXml != null && typeToast != null;

            typesResolved = true;

            typeManager = FindWinRtType("Windows.UI.Notifications.ToastNotificationManager",
                new string[] { "Windows.UI.Notifications", "Windows.UI", "Windows" });

            typeXml = FindWinRtType("Windows.Data.Xml.Dom.XmlDocument",
                new string[] { "Windows.Data.Xml.Dom", "Windows.Data", "Windows" });

            typeToast = FindWinRtType("Windows.UI.Notifications.ToastNotification",
                new string[] { "Windows.UI.Notifications", "Windows.UI", "Windows" });

            return typeManager != null && typeXml != null && typeToast != null;
        }

        static Type FindWinRtType(string typeName, string[] assemblies)
        {
            for (int i = 0; i < assemblies.Length; i++)
            {
                try
                {
                    Type t = Type.GetType(
                        typeName + ", " + assemblies[i] + ", ContentType=WindowsRuntime", false);
                    if (t != null)
                        return t;
                }
                catch { }
            }
            return null;
        }

        // Единая точка показа: сначала WinRT, при неудаче — NotifyIcon.
        public static void Show(NotifyIcon fallbackIcon, string title, string text, bool warning)
        {
            Log.Write("Show: запрошено уведомление \"" + title + "\"");

            if (TryShow(title, text))
                return;

            if (fallbackIcon != null)
            {
                Log.Write("Show: откат на воздушную подсказку NotifyIcon");
                fallbackIcon.ShowBalloonTip(15000, title, text,
                    warning ? ToolTipIcon.Warning : ToolTipIcon.Info);
            }
            else
            {
                Log.Write("Show: показать нечем — NotifyIcon недоступен");
            }
        }
    }
}
