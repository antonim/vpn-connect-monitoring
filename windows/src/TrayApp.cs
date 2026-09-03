using System;
using System.Drawing;
using System.Threading;
using System.Windows.Forms;

// System.Threading и System.Windows.Forms обе объявляют Timer; здесь нужен
// только оконный, работающий в UI-потоке.
using Timer = System.Windows.Forms.Timer;

namespace VpnConnectMonitoring
{
    public class TrayApp : ApplicationContext
    {
        readonly NotifyIcon tray;
        readonly Timer timer;
        readonly Icon iconOk;
        readonly Icon iconAlarm;
        readonly Icon iconIdle;

        readonly ToolStripMenuItem miPause;
        readonly ToolStripMenuItem miSound;
        readonly ToolStripMenuItem miStatus;

        Config config;
        SettingsForm settingsForm;
        HistoryForm historyForm;

        bool wasDown;
        DateTime lastAlert = DateTime.MinValue;
        DateTime pausedUntil = DateTime.MinValue;

        volatile bool showSettingsRequested;

        public TrayApp(bool openSettings, EventWaitHandle showSettingsSignal)
        {
            config = Config.Load();

            Notifier.EnsureRegistered();
            Shortcut.Ensure(System.Reflection.Assembly.GetExecutingAssembly().Location);
            if (Installer.AutostartEnabled)
                Shortcut.EnsureStartup(Installer.TargetExe);
            History.Prune();

            iconOk = Icons.Create(Icons.Ok, Icons.Glyph.Check);
            iconAlarm = Icons.Create(Icons.Alarm, Icons.Glyph.Bang);
            iconIdle = Icons.Create(Icons.Idle, Icons.Glyph.Dash);

            ContextMenuStrip menu = new ContextMenuStrip();

            miStatus = new ToolStripMenuItem("Проверка…");
            miStatus.Enabled = false;
            menu.Items.Add(miStatus);
            menu.Items.Add(new ToolStripSeparator());

            ToolStripMenuItem miHistory = new ToolStripMenuItem("Журнал подключения…");
            miHistory.Click += delegate { ShowHistory(); };
            menu.Items.Add(miHistory);

            ToolStripMenuItem miSettings = new ToolStripMenuItem("Настройки…");
            miSettings.Click += delegate { ShowSettings(); };
            menu.Items.Add(miSettings);

            ToolStripMenuItem miCheck = new ToolStripMenuItem("Проверить сейчас");
            miCheck.Click += delegate { Tick(true); };
            menu.Items.Add(miCheck);

            miPause = new ToolStripMenuItem("Пауза на 1 час");
            miPause.CheckOnClick = true;
            miPause.Click += MiPause_Click;
            menu.Items.Add(miPause);

            miSound = new ToolStripMenuItem("Звуковой сигнал");
            miSound.CheckOnClick = true;
            miSound.Checked = config.SoundEnabled;
            miSound.Click += MiSound_Click;
            menu.Items.Add(miSound);

            menu.Items.Add(new ToolStripSeparator());

            ToolStripMenuItem miExit = new ToolStripMenuItem("Выход");
            miExit.Click += delegate { ExitApp(); };
            menu.Items.Add(miExit);

            tray = new NotifyIcon();
            tray.Icon = iconIdle;
            tray.ContextMenuStrip = menu;
            tray.Visible = true;
            tray.DoubleClick += delegate { ShowHistory(); };
            tray.BalloonTipClicked += delegate { ShowHistory(); };
            tray.BalloonTipShown += delegate { Log.Write("NotifyIcon: BalloonTipShown"); };
            tray.BalloonTipClosed += delegate { Log.Write("NotifyIcon: BalloonTipClosed"); };

            timer = new Timer();
            timer.Interval = Math.Max(1, config.IntervalSeconds) * 1000;
            timer.Tick += delegate { Tick(false); };
            timer.Start();

            Tick(false);

            if (showSettingsSignal != null)
                StartSecondInstanceWatcher(showSettingsSignal);

            // При первом запуске (не из установленной папки) сразу показываем
            // настройки — иначе коллега не найдёт кнопку установки.
            if (openSettings)
                ShowSettings();
        }

        // Повторный запуск exe не поднимает второй экземпляр, а просит текущий
        // открыть настройки. Фоновый поток лишь взводит флаг; окно создаётся
        // в UI-потоке по таймеру, потому что WinForms не терпит обращений
        // к элементам управления извне.
        void StartSecondInstanceWatcher(EventWaitHandle signal)
        {
            Thread t = new Thread(delegate()
            {
                while (true)
                {
                    try
                    {
                        signal.WaitOne();
                        showSettingsRequested = true;
                    }
                    catch
                    {
                        return;
                    }
                }
            });
            t.IsBackground = true;
            t.Start();

            Timer poll = new Timer();
            poll.Interval = 400;
            poll.Tick += delegate
            {
                if (!showSettingsRequested)
                    return;
                showSettingsRequested = false;
                ShowSettings();
            };
            poll.Start();
        }

        // Переключатель в трее и флажок в настройках правят одно и то же
        // значение, поэтому изменение сразу пишется на диск — иначе
        // открытое следом окно настроек показало бы старое состояние.
        void MiSound_Click(object sender, EventArgs e)
        {
            config.SoundEnabled = miSound.Checked;

            try
            {
                config.Save();
            }
            catch (Exception ex)
            {
                Log.Write("MiSound: не удалось сохранить настройку — " + ex.Message);
            }

            Log.Write("Звуковой сигнал " + (config.SoundEnabled ? "включён" : "выключен")
                + " из меню в трее");

            // Короткий сигнал подтверждает, что звук снова работает.
            if (config.SoundEnabled)
                Sound.PlayRestore();
        }

        void MiPause_Click(object sender, EventArgs e)
        {
            pausedUntil = miPause.Checked ? DateTime.Now.AddHours(1) : DateTime.MinValue;
            Tick(false);
        }

        void ShowSettings()
        {
            if (settingsForm != null && !settingsForm.IsDisposed)
            {
                if (settingsForm.WindowState == FormWindowState.Minimized)
                    settingsForm.WindowState = FormWindowState.Normal;
                settingsForm.Activate();
                return;
            }

            settingsForm = new SettingsForm(config);
            settingsForm.ConfigSaved += ApplyConfig;
            settingsForm.HistoryRequested += delegate { ShowHistory(); };
            settingsForm.TestRequested += delegate
            {
                if (config.SoundEnabled)
                    Sound.PlayAlarm();
                Notifier.Show(tray, "Тест уведомления",
                    "Так будет выглядеть и звучать предупреждение об обрыве VPN.", true);
            };
            settingsForm.FormClosed += delegate { settingsForm = null; };
            settingsForm.Show();
            settingsForm.Activate();
        }

        void ShowHistory()
        {
            if (historyForm != null && !historyForm.IsDisposed)
            {
                if (historyForm.WindowState == FormWindowState.Minimized)
                    historyForm.WindowState = FormWindowState.Normal;
                historyForm.Activate();
                return;
            }

            historyForm = new HistoryForm();
            historyForm.FormClosed += delegate { historyForm = null; };
            historyForm.Show();
            historyForm.Activate();
        }

        void ApplyConfig(Config updated)
        {
            config = updated;
            miSound.Checked = config.SoundEnabled;

            timer.Stop();
            timer.Interval = Math.Max(1, config.IntervalSeconds) * 1000;
            timer.Start();

            // Новые настройки — новый повод предупредить, поэтому подавление
            // повторов сбрасываем.
            lastAlert = DateTime.MinValue;
            Tick(false);
        }

        void Tick(bool manual)
        {
            DateTime now = DateTime.Now;

            if (pausedUntil > now)
            {
                SetState(iconIdle, "Пауза до " + pausedUntil.ToString("HH:mm"));
                History.Record(now, VpnState.Unknown);
                return;
            }

            if (miPause.Checked)
            {
                miPause.Checked = false;
                pausedUntil = DateTime.MinValue;
            }

            if (!config.Enabled)
            {
                SetState(iconIdle, "Наблюдение выключено");
                History.Record(now, VpnState.Unknown);
                return;
            }

            // До первой настройки подключение не выбрано. Без этой проверки
            // пустое имя дало бы «не подключён» и сигнал тревоги каждую
            // минуту — на пустом месте.
            if (string.IsNullOrEmpty(config.VpnName))
            {
                SetState(iconIdle, "VPN-подключение не выбрано");
                History.Record(now, VpnState.Unknown);
                return;
            }

            if (!config.IsWithinSchedule(now) && !manual)
            {
                SetState(iconIdle, "Вне рабочего времени");
                History.Record(now, VpnState.Unknown);
                wasDown = false;
                return;
            }

            bool up = Vpn.IsConnected(config.VpnName);
            History.Record(now, up ? VpnState.Up : VpnState.Down);

            if (up)
            {
                SetState(iconOk, config.VpnName + ": подключён");

                if (wasDown && config.NotifyOnRestore)
                {
                    if (config.SoundEnabled)
                        Sound.PlayRestore();
                    Notifier.Show(tray, "VPN " + config.VpnName + " снова подключён",
                        "Связь восстановлена.", false);
                }
                wasDown = false;
                lastAlert = DateTime.MinValue;
                return;
            }

            SetState(iconAlarm, config.VpnName + ": НЕ подключён");

            bool suppressed = lastAlert != DateTime.MinValue
                && config.RepeatSuppressMinutes > 0
                && (now - lastAlert).TotalMinutes < config.RepeatSuppressMinutes;

            if (!suppressed)
            {
                if (config.SoundEnabled)
                    Sound.PlayAlarm();
                Notifier.Show(tray, "VPN " + config.VpnName + " не подключён!",
                    "Проверьте подключение — оно отвалилось.", true);
                lastAlert = now;
            }

            wasDown = true;
        }

        void SetState(Icon icon, string tip)
        {
            tray.Icon = icon;

            string text = Notifier.DisplayName + " — " + tip;
            // NotifyIcon.Text не принимает больше 63 символов и падает с
            // ArgumentException, если ограничение нарушено.
            if (text.Length > 63)
                text = text.Substring(0, 60) + "...";
            tray.Text = text;

            miStatus.Text = tip;
        }

        void ExitApp()
        {
            timer.Stop();

            // Отмечаем конец наблюдения, иначе на графике последнее известное
            // состояние тянулось бы до следующего запуска.
            History.Record(DateTime.Now, VpnState.Unknown);

            tray.Visible = false;
            tray.Dispose();
            ExitThread();
        }
    }
}
