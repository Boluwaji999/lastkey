# Builds dist/Lastkey.html: the whole app in one file that works offline, forever.
# Every library and font from lib/ is inlined. Run again after editing lastkey.html.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$utf8 = [System.Text.UTF8Encoding]::new($false)
$read = { param($p) [System.IO.File]::ReadAllText((Join-Path $root $p), [System.Text.Encoding]::UTF8) }

$page = & $read 'lastkey.html'

# Inline each <script src="lib/..."></script>. "</script" inside a library would end the tag early, so escape it.
$page = [regex]::Replace($page, '<script src="(lib/[^"]+)"></script>', {
  param($m)
  $js = (& $read $m.Groups[1].Value) -replace '</script', '<\/script' -replace '<!--', '<\!--'
  "<script>`n$js`n</script>"
})

# Swap the Google Fonts links for the embedded font files.
$page = [regex]::Replace($page, '(<link rel="preconnect"[^>]*>\s*)+<link rel="stylesheet" href="https://fonts\.googleapis\.com[^>]*>', {
  "<style>`n" + (& $read 'lib/fonts-inline.css') + "</style>"
})

foreach ($left in 'src="lib/', 'fonts.googleapis.com', 'cdn.jsdelivr', 'cdnjs.') {
  if ($page.Contains($left)) { throw "Build left an external reference: $left" }
}

$html = @"
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>[hidden]{display:none!important}body{margin:0}img{max-width:100%}</style>
</head>
<body>
$page
</body>
</html>
"@

New-Item -ItemType Directory -Force (Join-Path $root 'dist') | Out-Null
$out = Join-Path $root 'dist\Lastkey.html'
[System.IO.File]::WriteAllText($out, $html, $utf8)
$hash = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
Write-Host "Wrote dist\Lastkey.html ($([math]::Round((Get-Item $out).Length / 1KB)) KB)"
Write-Host "SHA-256: $hash"

# GitHub Pages serves docs/: the same bytes as index.html (to use online) and Lastkey.html (to download), plus the fingerprint.
$docs = Join-Path $root 'docs'
New-Item -ItemType Directory -Force $docs | Out-Null
Copy-Item $out (Join-Path $docs 'index.html') -Force
Copy-Item $out (Join-Path $docs 'Lastkey.html') -Force
[System.IO.File]::WriteAllText((Join-Path $docs 'SHA256SUMS.txt'), "$hash  Lastkey.html`n$hash  index.html`n", $utf8)
Write-Host "Updated docs\ for GitHub Pages"
