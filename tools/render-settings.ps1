#requires -Version 5.0
<#
    Отрисовывает окно настроек в PNG, не показывая его на экране.

    Нужно для проверки вёрстки: расположение элементов задано абсолютными
    координатами, поэтому после правок формы полезно посмотреть результат,
    не запуская приложение целиком.

    Использование:  .\tools\render-settings.ps1 [-Out путь.png]
#>

param(
    [ValidateSet('settings', 'history')]
    [string]$Which = 'settings',
    [string]$Out = ''
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$outDir = Join-Path $root 'build'
if ($Out -eq '') { $Out = Join-Path $outDir "$Which.png" }

$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { $csc = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$harness = Join-Path $outDir 'ShotHarness.exe'

# Program.cs исключаем — у обвязки собственная точка входа.
$sources = @(
    Get-ChildItem (Join-Path $root 'src') -Filter *.cs |
        Where-Object { $_.Name -ne 'Program.cs' } |
        ForEach-Object { $_.FullName }
)
$sources += Join-Path $root 'tools\Screenshot.cs'

& $csc /nologo /target:winexe /codepage:65001 /main:VpnConnectMonitoring.ShotProgram `
    "/out:$harness" /r:System.dll /r:System.Core.dll /r:System.Drawing.dll `
    /r:System.Windows.Forms.dll $sources
if ($LASTEXITCODE -ne 0) { throw "Компиляция обвязки завершилась с кодом $LASTEXITCODE" }

& $harness $Which $Out
Start-Sleep -Seconds 2
Remove-Item $harness -Force -ErrorAction SilentlyContinue

Write-Host "Готово: $Out" -ForegroundColor Green
