# Capture a rectangle of the screen into a PNG file, for the Power BI Desktop session (docs/desktop-session.md).
# It only reads pixels: it sends no input to any window and starts no program.
# Usage (Windows PowerShell 5.1 or PowerShell 7, from the repository root):
#   powershell -NoProfile -File tools/checks/capture_screen.ps1 -Out <png outside the repository> [-X 0 -Y 0 -Width 0 -Height 0]
# Without a size it captures the whole primary screen. Coordinates are physical pixels (the process is DPI aware).
param(
  [Parameter(Mandatory = $true)][string]$Out,
  [int]$X = 0,
  [int]$Y = 0,
  [int]$Width = 0,
  [int]$Height = 0
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$target = [System.IO.Path]::GetFullPath($Out)
if ($target.StartsWith($repo + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "capture_screen: -Out must lie outside the repository ($repo)"
}
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
public static class CaptureDpi {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
}
'@
[void][CaptureDpi]::SetProcessDPIAware()
if ($Width -le 0 -or $Height -le 0) {
  $X = 0
  $Y = 0
  $Width = [CaptureDpi]::GetSystemMetrics(0)
  $Height = [CaptureDpi]::GetSystemMetrics(1)
}
$folder = Split-Path -Parent $target
if ($folder) { [void](New-Item -ItemType Directory -Force -Path $folder) }
$bitmap = New-Object System.Drawing.Bitmap $Width, $Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
  $graphics.CopyFromScreen($X, $Y, 0, 0, $bitmap.Size)
  $bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
  $graphics.Dispose()
  $bitmap.Dispose()
}
Write-Output "captured ${Width}x${Height} at ${X},${Y} into $target"
