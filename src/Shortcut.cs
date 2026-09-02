using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace VpnConnectMonitoring
{
    // Ярлык в меню «Пуск» со свойством System.AppUserModel.ID.
    //
    // Для настольных (не упакованных) приложений Microsoft считает такой ярлык
    // условием показа уведомлений: именно по нему оболочка связывает процесс
    // с AppUserModelID. Регистрации в HKCU и вызова
    // SetCurrentProcessExplicitAppUserModelID по отдельности может не хватать,
    // а диагностировать это тяжело — при отказе Show() молчит.
    public static class Shortcut
    {
        const string FileName = "VPN Connect Monitoring.lnk";

        public static string Path_
        {
            get
            {
                return System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
                    "Programs", FileName);
            }
        }

        // Создаёт или обновляет ярлык на указанный exe. Идемпотентна.
        public static void Ensure(string exePath)
        {
            try
            {
                string lnk = Path_;
                string dir = System.IO.Path.GetDirectoryName(lnk);
                if (dir != null)
                    Directory.CreateDirectory(dir);

                object shellLink = new CShellLink();

                IShellLinkW link = (IShellLinkW)shellLink;
                link.SetPath(exePath);
                link.SetArguments("--tray");
                link.SetWorkingDirectory(System.IO.Path.GetDirectoryName(exePath));
                link.SetIconLocation(exePath, 0);
                link.SetDescription("Контроль подключения VPN в рабочее время");

                IPropertyStore store = (IPropertyStore)shellLink;
                PropertyKey key = AppUserModelIdKey();
                PropVariant pv = new PropVariant();
                pv.vt = VT_LPWSTR;
                pv.data = Marshal.StringToCoTaskMemUni(Notifier.AppId);
                try
                {
                    store.SetValue(ref key, ref pv);
                    store.Commit();
                }
                finally
                {
                    Marshal.FreeCoTaskMem(pv.data);
                }

                ((IPersistFile)shellLink).Save(lnk, true);
                Log.Write("Shortcut: ярлык обновлён -> " + lnk + " (цель " + exePath + ")");
            }
            catch (Exception ex)
            {
                Log.Write("Shortcut: не удалось создать ярлык — " + ex.Message);
            }
        }

        public static void Remove()
        {
            try
            {
                if (File.Exists(Path_))
                    File.Delete(Path_);
            }
            catch { }
        }

        // --- COM-интероп ------------------------------------------------------

        [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
        class CShellLink { }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
         Guid("000214F9-0000-0000-C000-000000000046")]
        interface IShellLinkW
        {
            void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile,
                int cch, IntPtr pfd, uint fFlags);
            void GetIDList(out IntPtr ppidl);
            void SetIDList(IntPtr pidl);
            void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cch);
            void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
            void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cch);
            void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
            void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cch);
            void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
            void GetHotkey(out short pwHotkey);
            void SetHotkey(short wHotkey);
            void GetShowCmd(out int piShowCmd);
            void SetShowCmd(int iShowCmd);
            void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath,
                int cch, out int piIcon);
            void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
            void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
            void Resolve(IntPtr hwnd, uint fFlags);
            void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
        }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
         Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")]
        interface IPropertyStore
        {
            void GetCount(out uint cProps);
            void GetAt(uint iProp, out PropertyKey pkey);
            void GetValue(ref PropertyKey key, out PropVariant pv);
            void SetValue(ref PropertyKey key, ref PropVariant pv);
            void Commit();
        }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
         Guid("0000010b-0000-0000-C000-000000000046")]
        interface IPersistFile
        {
            void GetClassID(out Guid pClassID);
            [PreserveSig] int IsDirty();
            void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
            void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName,
                [MarshalAs(UnmanagedType.Bool)] bool fRemember);
            void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
            void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        struct PropertyKey
        {
            public Guid fmtid;
            public uint pid;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct PropVariant
        {
            public ushort vt;
            public ushort r1, r2, r3;
            public IntPtr data;
            public IntPtr padding;
        }

        const ushort VT_LPWSTR = 31;

        static PropertyKey AppUserModelIdKey()
        {
            PropertyKey k = new PropertyKey();
            k.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
            k.pid = 5;
            return k;
        }
    }
}
