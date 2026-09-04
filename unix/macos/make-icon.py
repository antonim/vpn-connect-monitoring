#!/usr/bin/env python3
"""Рисует значок приложения и собирает AppIcon.icns.

Значок не хранится в репозитории готовым: 5 КБ скрипта вместо сотни
килобайт двоичных файлов, и рисунок нельзя случайно рассинхронизировать
с кодом, который его рисует. Сборка вызывает этот скрипт сама; вручную
он нужен, только чтобы посмотреть на результат.

Из внешнего требуются sips и iconutil — оба входят в macOS, а собирать
macOS-архив всё равно больше негде.

Никаких сторонних библиотек: PNG пишется вручную (формат простой —
zlib-поток и четыре блока), фигуры задаются функциями расстояния со
знаком. Такой способ даёт сглаживание без многократной передискретизации:
доля пикселя, попавшая внутрь фигуры, считается прямо из расстояния до
её края.

Рисунок: замок на скруглённом квадрате с вертикальным градиентом.
Замок читается как «защищённое соединение» и не разваливается в кашу
при 16 точках — в отличие от щита с галочкой, который на этом размере
превращается в пятно.
"""

import math
import os
import shutil
import struct
import subprocess
import sys
import zlib

SIZE = 1024

# Поля вокруг рисунка: у значков macOS сама картинка занимает не весь
# квадрат, иначе она смотрится крупнее соседей в Dock и Launchpad.
MARGIN = 100
CORNER = 185

TOP_COLOR = (78, 142, 255)
BOTTOM_COLOR = (26, 70, 196)

LOCK_COLOR = (255, 255, 255)

# Дужка замка
SHACKLE_CX, SHACKLE_CY = 512.0, 468.0
SHACKLE_OUTER, SHACKLE_INNER = 128.0, 74.0

# Корпус
BODY_CX, BODY_CY = 512.0, 620.0
BODY_HW, BODY_HH = 178.0, 152.0
BODY_R = 46.0

# Скважина
HOLE_CX, HOLE_CY, HOLE_R = 512.0, 586.0, 41.0
SLOT_CY, SLOT_HW, SLOT_HH, SLOT_R = 645.0, 17.0, 46.0, 16.0


def sd_rounded_rect(px, py, cx, cy, hw, hh, r):
    """Расстояние со знаком до скруглённого прямоугольника."""
    dx = abs(px - cx) - (hw - r)
    dy = abs(py - cy) - (hh - r)
    outside = math.hypot(max(dx, 0.0), max(dy, 0.0))
    inside = min(max(dx, dy), 0.0)
    return outside + inside - r


def sd_circle(px, py, cx, cy, r):
    return math.hypot(px - cx, py - cy) - r


def sd_arc(px, py):
    """Верхняя половина кольца — дужка замка.

    Нижняя половина не нужна: её закрывает корпус, а обрезать кольцо
    пересечением с полуплоскостью дешевле, чем описывать дужку кривыми.
    """
    ring = abs(math.hypot(px - SHACKLE_CX, py - SHACKLE_CY)
               - (SHACKLE_OUTER + SHACKLE_INNER) / 2.0) \
        - (SHACKLE_OUTER - SHACKLE_INNER) / 2.0
    return max(ring, py - SHACKLE_CY)


def coverage(distance):
    """Доля пикселя внутри фигуры. Полоса шириной в пиксель даёт сглаживание."""
    return min(1.0, max(0.0, 0.5 - distance))


def build_pixels():
    rows = []
    half = SIZE / 2.0
    hw = hh = half - MARGIN

    for y in range(SIZE):
        py = y + 0.5
        row = bytearray()

        # Градиент считается один раз на строку: он вертикальный.
        t = (py - MARGIN) / (SIZE - 2.0 * MARGIN)
        t = min(1.0, max(0.0, t))
        base = tuple(
            int(round(TOP_COLOR[i] + (BOTTOM_COLOR[i] - TOP_COLOR[i]) * t))
            for i in range(3)
        )

        for x in range(SIZE):
            px = x + 0.5

            plate = coverage(sd_rounded_rect(px, py, half, half, hw, hh, CORNER))
            if plate <= 0.0:
                row += b"\x00\x00\x00\x00"
                continue

            lock = max(
                coverage(sd_arc(px, py)),
                coverage(sd_rounded_rect(px, py, BODY_CX, BODY_CY,
                                         BODY_HW, BODY_HH, BODY_R)),
            )
            # Скважина вырезается из замка, а не рисуется поверх:
            # так сквозь неё виден градиент, как в настоящем отверстии.
            hole = max(
                coverage(sd_circle(px, py, HOLE_CX, HOLE_CY, HOLE_R)),
                coverage(sd_rounded_rect(px, py, HOLE_CX, SLOT_CY,
                                         SLOT_HW, SLOT_HH, SLOT_R)),
            )
            lock = max(0.0, lock - hole)

            row += bytes(
                int(round(base[i] + (LOCK_COLOR[i] - base[i]) * lock)) for i in range(3)
            )
            row.append(int(round(plate * 255)))

        rows.append(bytes(row))
    return rows


def write_png(path, rows):
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")

    with open(path, "wb") as fh:
        fh.write(png)


def build_icns(png_path, icns_path):
    if not shutil.which("sips") or not shutil.which("iconutil"):
        print("нет sips или iconutil — .icns не собран", file=sys.stderr)
        return False

    iconset = os.path.splitext(icns_path)[0] + ".iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)

    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            name = "icon_%dx%d%s.png" % (size, size, "@2x" if scale == 2 else "")
            subprocess.run(
                ["sips", "-z", str(size * scale), str(size * scale),
                 png_path, "--out", os.path.join(iconset, name)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            )

    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns_path], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return True


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    icns = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "AppIcon.icns")

    # PNG нужен только как исходник для iconutil, поэтому кладём его
    # рядом с результатом и убираем за собой.
    png = os.path.splitext(icns)[0] + ".png"
    keep_png = len(sys.argv) <= 1

    write_png(png, build_pixels())
    ok = build_icns(png, icns)
    if ok:
        print("значок собран: %s" % icns)
    if not keep_png:
        os.remove(png)
    elif ok:
        print("рисунок:       %s" % png)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
