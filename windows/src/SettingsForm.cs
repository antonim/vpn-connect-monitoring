using System;
using System.Collections.Generic;
using System.Drawing;
using System.Windows.Forms;

namespace VpnConnectMonitoring
{
    public class SettingsForm : Form
    {
        static readonly string[] DayNames = { "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс" };

        readonly Config config;

        ComboBox cbVpn;
        Label lblStatus;
        DateTimePicker dtStart;
        DateTimePicker dtEnd;
        CheckBox[] chkDays;
        NumericUpDown numInterval;
        NumericUpDown numRepeat;
        CheckBox chkRestore;
        CheckBox chkSound;
        CheckBox chkEnabled;
        Label lblInstall;
        Button btnInstall;
        CheckBox chkAutostart;
        Button btnLegacy;

        // Настройки применяются трей-приложением немедленно, без перезапуска.
        public event Action<Config> ConfigSaved;
        public event Action TestRequested;
        public event Action HistoryRequested;

        public SettingsForm(Config current)
        {
            config = current.Clone();
            BuildUi();
            LoadValues();
            RefreshStatus();
            RefreshInstallState();
        }

        void BuildUi()
        {
            Text = "VPN Connect Monitoring — настройки";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(470, 562);
            Font = new Font("Segoe UI", 9f);

            // --- Подключение ---
            GroupBox grpConn = new GroupBox();
            grpConn.Text = "Подключение";
            grpConn.SetBounds(12, 8, 446, 82);
            Controls.Add(grpConn);

            Label lblVpn = new Label();
            lblVpn.Text = "VPN-подключение:";
            lblVpn.SetBounds(14, 26, 130, 20);
            grpConn.Controls.Add(lblVpn);

            cbVpn = new ComboBox();
            cbVpn.DropDownStyle = ComboBoxStyle.DropDown;
            cbVpn.SetBounds(150, 22, 200, 24);
            cbVpn.TextChanged += delegate { RefreshStatus(); };
            grpConn.Controls.Add(cbVpn);

            Button btnCheck = new Button();
            btnCheck.Text = "Проверить";
            btnCheck.SetBounds(358, 21, 76, 26);
            btnCheck.Click += delegate { RefreshStatus(); };
            grpConn.Controls.Add(btnCheck);

            lblStatus = new Label();
            lblStatus.SetBounds(14, 54, 420, 20);
            grpConn.Controls.Add(lblStatus);

            // --- Расписание ---
            GroupBox grpSched = new GroupBox();
            grpSched.Text = "Расписание";
            grpSched.SetBounds(12, 98, 446, 132);
            Controls.Add(grpSched);

            Label lblHours = new Label();
            lblHours.Text = "Рабочие часы:";
            lblHours.SetBounds(14, 30, 130, 20);
            grpSched.Controls.Add(lblHours);

            dtStart = MakeTimePicker(150, 26);
            grpSched.Controls.Add(dtStart);

            Label lblDash = new Label();
            lblDash.Text = "—";
            lblDash.SetBounds(228, 30, 16, 20);
            grpSched.Controls.Add(lblDash);

            dtEnd = MakeTimePicker(248, 26);
            grpSched.Controls.Add(dtEnd);

            Label lblDays = new Label();
            lblDays.Text = "Дни недели:";
            lblDays.SetBounds(14, 62, 130, 20);
            grpSched.Controls.Add(lblDays);

            chkDays = new CheckBox[7];
            for (int i = 0; i < 7; i++)
            {
                chkDays[i] = new CheckBox();
                chkDays[i].Text = DayNames[i];
                chkDays[i].SetBounds(16 + i * 61, 88, 56, 22);
                grpSched.Controls.Add(chkDays[i]);
            }

            // --- Опрос и уведомления ---
            GroupBox grpPoll = new GroupBox();
            grpPoll.Text = "Опрос и уведомления";
            grpPoll.SetBounds(12, 238, 446, 158);
            Controls.Add(grpPoll);

            Label lblInterval = new Label();
            lblInterval.Text = "Интервал опроса:";
            lblInterval.SetBounds(14, 28, 130, 20);
            grpPoll.Controls.Add(lblInterval);

            numInterval = new NumericUpDown();
            numInterval.Minimum = 10;
            numInterval.Maximum = 3600;
            numInterval.Increment = 10;
            numInterval.SetBounds(150, 24, 70, 24);
            grpPoll.Controls.Add(numInterval);

            Label lblSec = new Label();
            lblSec.Text = "секунд";
            lblSec.SetBounds(226, 28, 90, 20);
            grpPoll.Controls.Add(lblSec);

            Label lblRepeat = new Label();
            lblRepeat.Text = "Не повторять чаще:";
            lblRepeat.SetBounds(14, 60, 130, 20);
            grpPoll.Controls.Add(lblRepeat);

            numRepeat = new NumericUpDown();
            numRepeat.Minimum = 0;
            numRepeat.Maximum = 240;
            numRepeat.SetBounds(150, 56, 70, 24);
            grpPoll.Controls.Add(numRepeat);

            Label lblMin = new Label();
            lblMin.Text = "минут (0 — при каждой проверке)";
            lblMin.SetBounds(226, 60, 210, 20);
            grpPoll.Controls.Add(lblMin);

            chkRestore = new CheckBox();
            chkRestore.Text = "Уведомлять о восстановлении связи";
            chkRestore.SetBounds(16, 86, 300, 22);
            grpPoll.Controls.Add(chkRestore);

            chkSound = new CheckBox();
            chkSound.Text = "Звуковой сигнал при обрыве и восстановлении";
            chkSound.SetBounds(16, 108, 380, 22);
            grpPoll.Controls.Add(chkSound);

            chkEnabled = new CheckBox();
            chkEnabled.Text = "Наблюдение включено";
            chkEnabled.SetBounds(16, 130, 300, 22);
            grpPoll.Controls.Add(chkEnabled);

            // --- Установка ---
            GroupBox grpInstall = new GroupBox();
            grpInstall.Text = "Установка";
            grpInstall.SetBounds(12, 404, 446, 108);
            Controls.Add(grpInstall);

            lblInstall = new Label();
            lblInstall.SetBounds(14, 22, 420, 20);
            grpInstall.Controls.Add(lblInstall);

            btnInstall = new Button();
            btnInstall.SetBounds(14, 46, 200, 28);
            btnInstall.Click += BtnInstall_Click;
            grpInstall.Controls.Add(btnInstall);

            btnLegacy = new Button();
            btnLegacy.Text = "Удалить старую задачу";
            btnLegacy.SetBounds(224, 46, 210, 28);
            btnLegacy.Click += BtnLegacy_Click;
            grpInstall.Controls.Add(btnLegacy);

            chkAutostart = new CheckBox();
            chkAutostart.Text = "Запускать при входе в Windows";
            chkAutostart.SetBounds(16, 80, 300, 22);
            chkAutostart.CheckedChanged += ChkAutostart_Changed;
            grpInstall.Controls.Add(chkAutostart);

            // --- Нижние кнопки ---
            Button btnTest = new Button();
            btnTest.Text = "Тест уведомления";
            btnTest.SetBounds(12, 522, 150, 30);
            btnTest.Click += delegate
            {
                Log.Write("SettingsForm: нажата кнопка «Тест уведомления», подписчиков="
                    + (TestRequested == null ? "0" : "есть"));
                if (TestRequested != null) TestRequested();
            };
            Controls.Add(btnTest);

            Button btnHistory = new Button();
            btnHistory.Text = "Журнал…";
            btnHistory.SetBounds(168, 522, 118, 30);
            btnHistory.Click += delegate { if (HistoryRequested != null) HistoryRequested(); };
            Controls.Add(btnHistory);

            Button btnSave = new Button();
            btnSave.Text = "Сохранить";
            btnSave.SetBounds(292, 522, 84, 30);
            btnSave.Click += BtnSave_Click;
            Controls.Add(btnSave);

            Button btnClose = new Button();
            btnClose.Text = "Закрыть";
            btnClose.SetBounds(382, 522, 76, 30);
            btnClose.Click += delegate { Close(); };
            Controls.Add(btnClose);

            AcceptButton = btnSave;
            CancelButton = btnClose;
        }

        static DateTimePicker MakeTimePicker(int x, int y)
        {
            DateTimePicker dt = new DateTimePicker();
            dt.Format = DateTimePickerFormat.Custom;
            dt.CustomFormat = "HH:mm";
            dt.ShowUpDown = true;
            dt.SetBounds(x, y, 72, 24);
            return dt;
        }

        void LoadValues()
        {
            List<string> entries = Vpn.ListEntries();
            cbVpn.Items.Clear();
            for (int i = 0; i < entries.Count; i++)
                cbVpn.Items.Add(entries[i]);

            // При первом запуске подключение не выбрано. Если оно в системе
            // всего одно, подставляем его: угадывать тут не из чего.
            if (string.IsNullOrEmpty(config.VpnName) && entries.Count == 1)
                cbVpn.Text = entries[0];
            else
                cbVpn.Text = config.VpnName;

            dtStart.Value = DateTime.Today.AddMinutes(config.WorkStartMinutes);
            dtEnd.Value = DateTime.Today.AddMinutes(config.WorkEndMinutes);

            for (int i = 0; i < 7; i++)
                chkDays[i].Checked = config.Days[i];

            numInterval.Value = config.IntervalSeconds;
            numRepeat.Value = config.RepeatSuppressMinutes;
            chkRestore.Checked = config.NotifyOnRestore;
            chkSound.Checked = config.SoundEnabled;
            chkEnabled.Checked = config.Enabled;
        }

        void RefreshStatus()
        {
            string name = cbVpn.Text.Trim();
            if (name.Length == 0)
            {
                lblStatus.Text = "Статус: имя подключения не указано";
                lblStatus.ForeColor = Color.FromArgb(140, 90, 0);
                return;
            }

            if (Vpn.IsConnected(name))
            {
                lblStatus.Text = "Статус: подключено";
                lblStatus.ForeColor = Icons.Ok;
            }
            else
            {
                lblStatus.Text = "Статус: не подключено";
                lblStatus.ForeColor = Icons.Alarm;
            }
        }

        void RefreshInstallState()
        {
            bool installed = Installer.IsInstalled;

            if (installed)
            {
                lblInstall.Text = "Установлено в: " + Installer.InstallDir;
                btnInstall.Text = "Удалить из системы";
            }
            else
            {
                lblInstall.Text = "Не установлено — работает из текущей папки.";
                btnInstall.Text = "Установить в систему";
            }

            chkAutostart.CheckedChanged -= ChkAutostart_Changed;
            chkAutostart.Checked = Installer.AutostartEnabled;
            chkAutostart.Enabled = installed;
            chkAutostart.CheckedChanged += ChkAutostart_Changed;

            btnLegacy.Visible = Installer.LegacyTaskExists();
        }

        void ChkAutostart_Changed(object sender, EventArgs e)
        {
            try
            {
                Installer.SetAutostart(chkAutostart.Checked, Installer.TargetExe);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Не удалось изменить автозапуск:\n" + ex.Message,
                    Notifier.DisplayName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        void BtnInstall_Click(object sender, EventArgs e)
        {
            if (Installer.IsInstalled)
            {
                DialogResult r = MessageBox.Show(this,
                    "Удалить VPN Connect Monitoring из системы?\n\n" +
                    "Будут сняты автозапуск и установленная копия программы.\n" +
                    "Настройки сохранятся — при повторной установке они подхватятся.",
                    Notifier.DisplayName, MessageBoxButtons.YesNo, MessageBoxIcon.Question);

                if (r != DialogResult.Yes)
                    return;

                Installer.Uninstall(false);
                MessageBox.Show(this, "Удалено. Приложение сейчас закроется.",
                    Notifier.DisplayName, MessageBoxButtons.OK, MessageBoxIcon.Information);
                Application.Exit();
                return;
            }

            try
            {
                config.Save();
                string exe = Installer.Install();

                MessageBox.Show(this,
                    "Установлено:\n" + exe + "\n\n" +
                    "Добавлен автозапуск при входе в Windows.\n" +
                    "Сейчас запустится установленная копия.",
                    Notifier.DisplayName, MessageBoxButtons.OK, MessageBoxIcon.Information);

                if (!Installer.IsRunningFromInstallDir)
                {
                    System.Diagnostics.Process.Start(exe, "--tray");
                    Application.Exit();
                    return;
                }

                RefreshInstallState();
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Не удалось установить:\n" + ex.Message,
                    Notifier.DisplayName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        void BtnLegacy_Click(object sender, EventArgs e)
        {
            DialogResult r = MessageBox.Show(this,
                "Удалить задачу планировщика \"" + Installer.LegacyTaskName + "\"?\n\n" +
                "Это прежняя версия решения на PowerShell. Пока она включена,\n" +
                "уведомления будут приходить дважды.",
                Notifier.DisplayName, MessageBoxButtons.YesNo, MessageBoxIcon.Question);

            if (r != DialogResult.Yes)
                return;

            if (Installer.RemoveLegacyTask())
            {
                MessageBox.Show(this, "Задача удалена.", Notifier.DisplayName,
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                RefreshInstallState();
            }
            else
            {
                MessageBox.Show(this, "Не удалось удалить задачу.", Notifier.DisplayName,
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        void BtnSave_Click(object sender, EventArgs e)
        {
            string name = cbVpn.Text.Trim();
            if (name.Length == 0)
            {
                MessageBox.Show(this, "Укажите имя VPN-подключения.", Notifier.DisplayName,
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            bool anyDay = false;
            for (int i = 0; i < 7; i++)
                if (chkDays[i].Checked) anyDay = true;

            if (!anyDay)
            {
                MessageBox.Show(this, "Выберите хотя бы один день недели.", Notifier.DisplayName,
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            config.VpnName = name;
            config.WorkStartMinutes = dtStart.Value.Hour * 60 + dtStart.Value.Minute;
            config.WorkEndMinutes = dtEnd.Value.Hour * 60 + dtEnd.Value.Minute;
            for (int i = 0; i < 7; i++)
                config.Days[i] = chkDays[i].Checked;
            config.IntervalSeconds = (int)numInterval.Value;
            config.RepeatSuppressMinutes = (int)numRepeat.Value;
            config.NotifyOnRestore = chkRestore.Checked;
            config.SoundEnabled = chkSound.Checked;
            config.Enabled = chkEnabled.Checked;

            try
            {
                config.Save();
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Не удалось сохранить настройки:\n" + ex.Message,
                    Notifier.DisplayName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            if (ConfigSaved != null)
                ConfigSaved(config.Clone());

            Close();
        }
    }
}
