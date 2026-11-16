$ErrorActionPreference = 'Stop'
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe = Join-Path $AppDir 'PSrazmer_PRO.exe'
$Icon = Join-Path $AppDir 'Resources\PSrazmer.ico'
if (!(Test-Path $Exe)) { throw "Не найден файл: $Exe. Скопируйте этот скрипт в папку с PSrazmer_PRO.exe." }
if (!(Test-Path $Icon)) { throw "Не найден значок: $Icon" }
$Wsh = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath('Desktop')
$StartMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'PSразмер изображений PRO'
New-Item -ItemType Directory -Force -Path $StartMenu | Out-Null
foreach ($Target in @((Join-Path $Desktop 'PSразмер изображений PRO.lnk'), (Join-Path $StartMenu 'PSразмер изображений PRO.lnk'))) {
  $Shortcut = $Wsh.CreateShortcut($Target)
  $Shortcut.TargetPath = $Exe
  $Shortcut.WorkingDirectory = $AppDir
  $Shortcut.IconLocation = "$Icon,0"
  $Shortcut.Description = 'Локальная обработка и изменение размера фотографий'
  $Shortcut.Save()
}
Write-Host 'Ярлыки рабочего стола и меню Пуск созданы.' -ForegroundColor Green
