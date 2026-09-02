using System;
using System.IO;
using System.Media;

namespace VpnConnectMonitoring
{
    // Звук синтезируется в памяти, а не берётся из системных схем.
    //
    // Причина: стандартные звуки Windows слух отфильтровывает как фон — их
    // выдают десятки приложений в день. Нисходящий мотив звучит непривычно
    // и читается как «что-то отвалилось», а восходящий — как «вернулось».
    // Заодно это избавляет от необходимости класть рядом с exe файлы .wav.
    public static class Sound
    {
        const int SampleRate = 44100;

        static byte[] alarmWav;
        static byte[] restoreWav;

        public static void PlayAlarm()
        {
            if (alarmWav == null)
            {
                // Три нисходящих тона, повторённые дважды.
                alarmWav = BuildWav(
                    new double[] { 988, 740, 554, 0, 988, 740, 554 },
                    new int[] { 170, 170, 260, 90, 170, 170, 420 });
            }
            Play(alarmWav);
        }

        public static void PlayRestore()
        {
            if (restoreWav == null)
            {
                restoreWav = BuildWav(
                    new double[] { 554, 740, 988 },
                    new int[] { 130, 130, 260 });
            }
            Play(restoreWav);
        }

        static void Play(byte[] wav)
        {
            try
            {
                // Play() проигрывает асинхронно и не блокирует UI-поток.
                SoundPlayer player = new SoundPlayer(new MemoryStream(wav));
                player.Play();
            }
            catch (Exception ex)
            {
                Log.Write("Sound: не удалось воспроизвести — " + ex.Message);
            }
        }

        // Частота 0 означает паузу.
        static byte[] BuildWav(double[] freqs, int[] durationsMs)
        {
            int total = 0;
            int[] counts = new int[freqs.Length];
            for (int i = 0; i < freqs.Length; i++)
            {
                counts[i] = SampleRate * durationsMs[i] / 1000;
                total += counts[i];
            }

            short[] pcm = new short[total];
            int idx = 0;

            for (int i = 0; i < freqs.Length; i++)
            {
                int n = counts[i];
                if (freqs[i] <= 0)
                {
                    idx += n;
                    continue;
                }

                // Плавные фронты обязательны: обрыв синусоиды на ненулевой
                // амплитуде даёт щелчок в динамике.
                int fade = Math.Min(600, n / 4);

                for (int s = 0; s < n; s++)
                {
                    double env = 1.0;
                    if (s < fade) env = (double)s / fade;
                    else if (s > n - fade) env = (double)(n - s) / fade;

                    double v = Math.Sin(2.0 * Math.PI * freqs[i] * s / SampleRate) * 0.55 * env;
                    pcm[idx++] = (short)(v * short.MaxValue);
                }
            }

            return WrapRiff(pcm);
        }

        static byte[] WrapRiff(short[] pcm)
        {
            MemoryStream ms = new MemoryStream();
            BinaryWriter w = new BinaryWriter(ms);

            int dataBytes = pcm.Length * 2;
            const short channels = 1;
            const short bits = 16;

            w.Write(new char[] { 'R', 'I', 'F', 'F' });
            w.Write(36 + dataBytes);
            w.Write(new char[] { 'W', 'A', 'V', 'E' });

            w.Write(new char[] { 'f', 'm', 't', ' ' });
            w.Write(16);                                   // размер блока fmt
            w.Write((short)1);                             // PCM
            w.Write(channels);
            w.Write(SampleRate);
            w.Write(SampleRate * channels * bits / 8);     // байт в секунду
            w.Write((short)(channels * bits / 8));         // выравнивание блока
            w.Write(bits);

            w.Write(new char[] { 'd', 'a', 't', 'a' });
            w.Write(dataBytes);
            for (int i = 0; i < pcm.Length; i++)
                w.Write(pcm[i]);

            w.Flush();
            return ms.ToArray();
        }
    }
}
