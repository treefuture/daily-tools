@echo off
echo Generating extension icons using PowerShell...
echo.

powershell.exe -Command ^
  $sizes = @(16, 48, 128); ^
  $svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" rx="20" fill="#4488ff"/><circle cx="64" cy="52" r="22" fill="none" stroke="#fff" stroke-width="5"/><path d="M42 82 L86 82 M64 68 L64 96" stroke="#fff" stroke-width="5" stroke-linecap="round"/></svg>'; ^
  Add-Type -AssemblyName System.Drawing; ^
  $wc = New-Object System.Net.WebClient; ^
  $tempSvg = [System.IO.Path]::GetTempFileName() + '.svg'; ^
  Set-Content -Path $tempSvg -Value $svg -Encoding UTF8; ^
  foreach ($s in $sizes) { ^
    $bmp = New-Object System.Drawing.Bitmap($s, $s); ^
    $g = [System.Drawing.Graphics]::FromImage($bmp); ^
    $g.SmoothingMode = 'HighQuality'; ^
    $r = [System.Drawing.Rectangle]::FromLTRB(0, 0, $s, $s); ^
    $g.FillRectangle([System.Drawing.SolidBrush][System.Drawing.Color]::FromArgb(255,68,136,255), $r); ^
    $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, [Math]::Max(1, $s/25)); ^
    $cx = $s/2; $cy = $s*0.41; $cr = $s*0.17; ^
    $g.DrawEllipse($pen, $cx-$cr, $cy-$cr, $cr*2, $cr*2); ^
    $g.DrawLine($pen, $s*0.33, $s*0.64, $s*0.67, $s*0.64); ^
    $g.DrawLine($pen, $cx, $s*0.53, $cx, $s*0.75); ^
    $g.Dispose(); ^
    $out = Join-Path "%~dp0" ('icon' + $s + '.png'); ^
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png); ^
    $bmp.Dispose(); ^
    echo Created icon%$s%.png; ^
  }; ^
  Remove-Item $tempSvg -ErrorAction SilentlyContinue; ^
  echo Done!;

if %errorlevel% neq 0 (
  echo.
  echo Failed to generate icons. Make sure PowerShell is available.
  echo You can manually create PNG icons (16x16, 48x48, 128x128) in the icons folder.
)
pause
