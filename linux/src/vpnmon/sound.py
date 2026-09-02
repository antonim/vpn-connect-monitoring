"""Звуковой сигнал.

Волна синтезируется в памяти, а не берётся из системной схемы: штатные
звуки Ubuntu слух отфильтровывает как фон. Нисходящий мотив читается как
«что-то отвалилось», восходящий — как «вернулось». Файлы .wav в пакете
держать не нужно, они собираются при первом воспроизведении.

Мотивы совпадают с Windows-версией, чтобы сигнал узнавался одинаково
на обеих платформах.
"""

import array
import math
import os
import shutil
import struct
import subprocess
import tempfile

SAMPLE_RATE = 44100

# (частота Гц, длительность мс); частота 0 — пауза
ALARM = [(988, 170), (740, 170), (554, 260), (0, 90), (988, 170), (740, 170), (554, 420)]
RESTORE = [(554, 130), (740, 130), (988, 260)]

# Проигрыватели в порядке предпочтения: PipeWire, PulseAudio, ALSA.
PLAYERS = (
    ("pw-play", []),
    ("paplay", []),
    ("aplay", ["-q"]),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
)

_cache = {}


def _build_wav(motif):
    samples = array.array("h")

    for freq, ms in motif:
        count = SAMPLE_RATE * ms // 1000
        if freq <= 0:
            samples.extend([0] * count)
            continue

        # Плавные фронты обязательны: обрыв синусоиды на ненулевой амплитуде
        # даёт щелчок в динамике.
        fade = min(600, count // 4) or 1

        for i in range(count):
            if i < fade:
                env = i / fade
            elif i > count - fade:
                env = (count - i) / fade
            else:
                env = 1.0
            value = math.sin(2.0 * math.pi * freq * i / SAMPLE_RATE) * 0.55 * env
            samples.append(int(value * 32767))

    data = samples.tobytes()
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + data


def _wav_path(name, motif):
    if name in _cache and os.path.exists(_cache[name]):
        return _cache[name]

    directory = os.path.join(tempfile.gettempdir(), "vpn-connect-monitoring")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "%s.wav" % name)

    with open(path, "wb") as fh:
        fh.write(_build_wav(motif))

    _cache[name] = path
    return path


def available():
    return any(shutil.which(player) for player, _ in PLAYERS)


def _play_file(path):
    for player, args in PLAYERS:
        exe = shutil.which(player)
        if not exe:
            continue
        try:
            # Не ждём завершения: сигнал не должен подвешивать опрос.
            subprocess.Popen(
                [exe] + args + [path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            continue
    return False


def play_alarm():
    return _play_file(_wav_path("alarm", ALARM))


def play_restore():
    return _play_file(_wav_path("restore", RESTORE))
