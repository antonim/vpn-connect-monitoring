#requires -Version 5.0
<#
    Сборка VpnConnectMonitoring.exe.

    Используется csc.exe из состава Windows (.NET Framework 4.x), поэтому
    ставить .NET SDK не нужно. Компилятор поддерживает только C# 5 —
    в исходниках нет интерполяции строк, ?. и прочего синтаксиса новее.

    -Install   после сборки обновить установленную копию в %LOCALAPPDATA%
               и перезапустить приложение. Без этого ключа сборка кладёт
               exe только в build\, а работающая система остаётся на старой
               версии — на этом легко обмануться.
#>

param([switch]$Install)

$ErrorActionPreference = 'Stop'

$root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcDir  = Join-Path $root 'src'
$outDir  = Join-Path $root 'build'
$iconPath = Join-Path $outDir 'app.ico'
$exePath = Join-Path $outDir 'VpnConnectMonitoring.exe'

$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) {
    $csc = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
if (-not (Test-Path $csc)) {
    throw "csc.exe не найден. Требуется .NET Framework 4.x (входит в Windows 10/11)."
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# --- Значок приложения ---------------------------------------------------
# Генерируем сами, чтобы в репозитории не лежали бинарные ресурсы.

Add-Type -AssemblyName System.Drawing

# csc.exe умеет только классические DIB-записи внутри .ico: PNG-сжатые
# кадры (Vista+) он отвергает с "Недопустимые данные". Поэтому каждый размер
# кодируем как BITMAPINFOHEADER + BGRA снизу вверх + пустая AND-маска.
function New-IconDib {
    param([int]$Size)

    $bmp = New-Object System.Drawing.Bitmap($Size, $Size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
        $g.Clear([System.Drawing.Color]::Transparent)

        $fill = [System.Drawing.Color]::FromArgb(46, 160, 67)
        $brush = New-Object System.Drawing.SolidBrush($fill)
        $g.FillEllipse($brush, 0.5, 0.5, $Size - 1.5, $Size - 1.5)
        $brush.Dispose()

        $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(70, 0, 0, 0), [float]($Size / 16))
        $g.DrawEllipse($pen, 1.0, 1.0, $Size - 2.5, $Size - 2.5)
        $pen.Dispose()

        # Галочка вместо надписи: «VPN» шрифтом, читаемым в мелких размерах,
        # в кружок не помещается и переносится на две строки. Форма совпадает
        # со значком «связь есть» в трее — см. Icons.cs.
        $k = $Size / 32.0
        $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, [float](4 * $k))
        $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $pen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
        $points = @(
            (New-Object System.Drawing.PointF([float](9 * $k), [float](16.5 * $k))),
            (New-Object System.Drawing.PointF([float](14 * $k), [float](21.5 * $k))),
            (New-Object System.Drawing.PointF([float](23 * $k), [float](11 * $k)))
        )
        $g.DrawLines($pen, [System.Drawing.PointF[]]$points)
        $pen.Dispose()

        $rect = New-Object System.Drawing.Rectangle(0, 0, $Size, $Size)
        $locked = $bmp.LockBits($rect,
            [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
            [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $stride = $locked.Stride
        $pixels = New-Object byte[] ($stride * $Size)
        [System.Runtime.InteropServices.Marshal]::Copy($locked.Scan0, $pixels, 0, $pixels.Length)
        $bmp.UnlockBits($locked)

        $ms = New-Object System.IO.MemoryStream
        $bw = New-Object System.IO.BinaryWriter($ms)
        try {
            # BITMAPINFOHEADER: высота удвоена, так как за цветом идёт маска.
            $bw.Write([UInt32]40)
            $bw.Write([Int32]$Size)
            $bw.Write([Int32]($Size * 2))
            $bw.Write([UInt16]1)
            $bw.Write([UInt16]32)
            $bw.Write([UInt32]0)          # BI_RGB
            $bw.Write([UInt32]0)          # biSizeImage
            $bw.Write([Int32]0); $bw.Write([Int32]0)
            $bw.Write([UInt32]0); $bw.Write([UInt32]0)

            # DIB хранится снизу вверх.
            $rowBytes = $Size * 4
            for ($y = $Size - 1; $y -ge 0; $y--) {
                $bw.Write($pixels, $y * $stride, $rowBytes)
            }

            # AND-маска не нужна при 32 bpp, но структурно обязана присутствовать.
            $maskRow = [int][math]::Ceiling($Size / 32.0) * 4
            $zeros = New-Object byte[] ($maskRow * $Size)
            $bw.Write($zeros)

            $bw.Flush()
            # Запятая обязательна: иначе PowerShell развернёт массив в конвейер
            # и на выходе получится Object[], который BinaryWriter не примет
            # как byte[].
            return ,$ms.ToArray()
        }
        finally {
            $bw.Dispose()
        }
    }
    finally {
        $g.Dispose()
        $bmp.Dispose()
    }
}

function Write-IcoFile {
    param([string]$Path, [int[]]$Sizes)

    $images = @()
    foreach ($s in $Sizes) {
        $images += ,@{ Size = $s; Data = (New-IconDib -Size $s) }
    }

    $fs = [System.IO.File]::Create($Path)
    $bw = New-Object System.IO.BinaryWriter($fs)
    try {
        # ICONDIR
        $bw.Write([UInt16]0)                 # reserved
        $bw.Write([UInt16]1)                 # type: icon
        $bw.Write([UInt16]$images.Count)

        # Данные кадров кладём после каталога записей.
        $offset = 6 + 16 * $images.Count
        foreach ($img in $images) {
            $dim = $img.Size
            if ($dim -ge 256) { $dim = 0 }   # 256 кодируется нулём

            $bw.Write([Byte]$dim)            # width
            $bw.Write([Byte]$dim)            # height
            $bw.Write([Byte]0)               # palette
            $bw.Write([Byte]0)               # reserved
            $bw.Write([UInt16]1)             # planes
            $bw.Write([UInt16]32)            # bpp
            $bw.Write([UInt32]$img.Data.Length)
            $bw.Write([UInt32]$offset)
            $offset += $img.Data.Length
        }

        foreach ($img in $images) {
            $bw.Write([byte[]]$img.Data)
        }
    }
    finally {
        $bw.Dispose()
        $fs.Dispose()
    }
}

Write-Host 'Генерация значка...' -ForegroundColor Cyan
# 256×256 намеренно не включаем: без PNG-сжатия такой кадр весит 270 КБ и
# раздувает exe почти в десять раз ради режима «огромные значки».
Write-IcoFile -Path $iconPath -Sizes @(16, 32, 48, 64)

# --- Компиляция ----------------------------------------------------------

$sources = Get-ChildItem -Path $srcDir -Filter *.cs | ForEach-Object { $_.FullName }
if ($sources.Count -eq 0) {
    throw "В папке $srcDir нет файлов .cs"
}

$cscArgs = @(
    '/nologo'
    '/target:winexe'
    '/platform:anycpu'
    '/optimize+'
    '/warn:4'
    '/codepage:65001'          # исходники в UTF-8 без BOM
    "/win32icon:$iconPath"
    "/out:$exePath"
    '/r:System.dll'
    '/r:System.Core.dll'
    '/r:System.Drawing.dll'
    '/r:System.Windows.Forms.dll'
) + $sources

Write-Host 'Компиляция...' -ForegroundColor Cyan
& $csc $cscArgs
if ($LASTEXITCODE -ne 0) {
    throw "Компиляция завершилась с кодом $LASTEXITCODE"
}

$size = [math]::Round((Get-Item $exePath).Length / 1KB, 1)
Write-Host ''
Write-Host "Готово: $exePath ($size КБ)" -ForegroundColor Green

# --- Обновление установленной копии --------------------------------------

$installedExe = Join-Path $env:LOCALAPPDATA 'Programs\VpnConnectMonitoring\VpnConnectMonitoring.exe'

if ($Install) {
    # Работающий exe перезаписать нельзя — файл заблокирован.
    $running = @(Get-Process VpnConnectMonitoring -ErrorAction SilentlyContinue)
    $wasRunning = $running.Count -gt 0
    if ($wasRunning) {
        Write-Host 'Останавливаю запущенное приложение...' -ForegroundColor Cyan
        $running | Stop-Process -Force
        Start-Sleep -Seconds 2
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $installedExe) | Out-Null
    Copy-Item $exePath $installedExe -Force
    Write-Host "Обновлено: $installedExe" -ForegroundColor Green

    Set-ItemProperty -Path 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run' `
        -Name 'VpnConnectMonitoring' -Value "`"$installedExe`" --tray"

    Start-Process -FilePath $installedExe -ArgumentList '--tray' | Out-Null
    Write-Host 'Приложение перезапущено.' -ForegroundColor Green
}
elseif (Test-Path $installedExe) {
    # Молчаливое расхождение версий — самая неприятная ошибка здесь:
    # правки внесены, сборка прошла, а поведение не меняется.
    if ((Get-Item $installedExe).LastWriteTime -lt (Get-Item $exePath).LastWriteTime) {
        Write-Host ''
        Write-Host 'ВНИМАНИЕ: установленная копия старее свежей сборки.' -ForegroundColor Yellow
        Write-Host "  $installedExe" -ForegroundColor Yellow
        Write-Host '  Обновить и перезапустить:  .\build.ps1 -Install' -ForegroundColor Yellow
    }
}
