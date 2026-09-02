using System;
using System.Collections.Generic;
using System.IO;
using System.Net.NetworkInformation;
using System.Text;

namespace VpnConnectMonitoring
{
    public static class Vpn
    {
        // Подключённое RAS-соединение поднимает сетевой интерфейс со своим
        // именем; в отключённом состоянии интерфейс исчезает целиком. Это
        // проверено на связке AVIA (Connected -> интерфейс Ppp/Up) и
        // ALFA_METRICS (Disconnected -> интерфейса нет).
        //
        // NetworkInterface выбран вместо RasEnumConnections намеренно: размер
        // структуры RASCONN менялся между версиями Windows, и при несовпадении
        // dwSize API возвращает ERROR_INVALID_SIZE. Здесь такой зависимости нет.
        public static bool IsConnected(string vpnName)
        {
            if (string.IsNullOrEmpty(vpnName))
                return false;

            try
            {
                NetworkInterface[] all = NetworkInterface.GetAllNetworkInterfaces();
                for (int i = 0; i < all.Length; i++)
                {
                    if (string.Equals(all[i].Name, vpnName, StringComparison.OrdinalIgnoreCase)
                        && all[i].OperationalStatus == OperationalStatus.Up)
                    {
                        return true;
                    }
                }
            }
            catch
            {
                // Если перечислить интерфейсы не удалось, честнее считать
                // состояние неизвестным, чем поднимать ложную тревогу.
                return true;
            }
            return false;
        }

        // Имена VPN-подключений берём из телефонной книги RAS: пользовательской
        // и общесистемной (второй на многих машинах просто нет).
        public static List<string> ListEntries()
        {
            List<string> names = new List<string>();

            string userPbk = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                @"Microsoft\Network\Connections\Pbk\rasphone.pbk");

            string allUsersPbk = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                @"Microsoft\Network\Connections\Pbk\rasphone.pbk");

            AddEntriesFrom(userPbk, names);
            AddEntriesFrom(allUsersPbk, names);
            return names;
        }

        static void AddEntriesFrom(string pbkPath, List<string> names)
        {
            try
            {
                if (!File.Exists(pbkPath))
                    return;

                foreach (string raw in File.ReadAllLines(pbkPath, Encoding.Default))
                {
                    string line = raw.Trim();
                    if (line.Length < 3 || line[0] != '[' || line[line.Length - 1] != ']')
                        continue;

                    string name = line.Substring(1, line.Length - 2).Trim();
                    if (name.Length == 0)
                        continue;

                    bool exists = false;
                    for (int i = 0; i < names.Count; i++)
                    {
                        if (string.Equals(names[i], name, StringComparison.OrdinalIgnoreCase))
                        {
                            exists = true;
                            break;
                        }
                    }
                    if (!exists)
                        names.Add(name);
                }
            }
            catch
            {
                // Недоступная телефонная книга — не повод падать: имя VPN
                // всегда можно ввести в поле вручную.
            }
        }
    }
}
