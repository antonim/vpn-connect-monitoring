#requires -Version 5.0
<#
    Рисует значки трея в один PNG для визуальной проверки.

    Нужно потому, что в панели задач значок отрисовывается примерно
    в 16 пикселей, и то, что выглядит нормально на 32, там может
    превратиться в кашу — так и случилось с надписью «VPN».

    Использование:  .\tools\render-icons.ps1 [-Out путь.png]
#>

param([string]$Out = '')

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$outDir = Join-Path $root 'build'
if ($Out -eq '') { $Out = Join-Path $outDir 'icons.png' }

$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { $csc = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$harness = Join-Path $outDir 'IconPreview.exe'

$sources = @(
    (Join-Path $root 'src\Icons.cs'),
    (Join-Path $root 'tools\IconPreview.cs')
)

& $csc /nologo /target:exe /codepage:65001 /main:VpnConnectMonitoring.IconPreviewProgram `
    "/out:$harness" /r:System.dll /r:System.Drawing.dll $sources
if ($LASTEXITCODE -ne 0) { throw "Компиляция обвязки завершилась с кодом $LASTEXITCODE" }

& $harness $Out
Start-Sleep -Seconds 1
Remove-Item $harness -Force -ErrorAction SilentlyContinue

Write-Host "Готово: $Out" -ForegroundColor Green
