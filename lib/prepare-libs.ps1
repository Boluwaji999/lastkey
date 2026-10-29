# One-time step: turns the downloaded vendor files into what Lastkey embeds.
#   tlock.bundle.mjs (esm.sh bundle of tlock-js@0.9.0) -> tlock.js, a classic script that sets window.tlock
#   fonts.css (Google Fonts, latin + latin-ext only) -> fonts-inline.css with the font files as data URIs
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot

# --- tlock: wrap the ES module in a function and turn its export clause into window.tlock ---
$src = [System.IO.File]::ReadAllText((Join-Path $dir 'tlock.bundle.mjs'))
$m = [regex]::Match($src, 'export\{([^}]+)\};')
if (-not $m.Success) { throw 'Export clause not found in tlock.bundle.mjs' }
$pairs = $m.Groups[1].Value -split ',' | ForEach-Object {
  $p = $_.Trim() -split '\s+as\s+'
  if ($p[1] -ne '__esModule') { "$($p[1]):$($p[0])" }
}
$body = $src.Remove($m.Index, $m.Length).Insert($m.Index, "window.tlock={$($pairs -join ',')};")
$body = $body -replace '//# sourceMappingURL=\S+', ''
$out = "/* tlock-js 0.9.0 (drand, Apache-2.0/MIT), bundled by esm.sh, wrapped for inline use */`n(function(){`"use strict`";`n$body`n})();`n"
[System.IO.File]::WriteAllText((Join-Path $dir 'tlock.js'), $out, [System.Text.UTF8Encoding]::new($false))

# --- fonts: one @font-face per font file, with a weight range, embedded as base64 ---
$css = [System.IO.File]::ReadAllText((Join-Path $dir 'fonts.css'))
$blocks = [regex]::Matches($css, '/\* (latin|latin-ext) \*/\s*@font-face \{[^}]+\}')
$faces = [ordered]@{}
foreach ($b in $blocks) {
  $v = $b.Value
  $url = [regex]::Match($v, 'url\(([^)]+)\)').Groups[1].Value
  $w = [int][regex]::Match($v, 'font-weight: (\d+)').Groups[1].Value
  if (-not $faces.Contains($url)) {
    $faces[$url] = @{
      family = [regex]::Match($v, "font-family: '([^']+)'").Groups[1].Value
      range  = [regex]::Match($v, 'unicode-range: ([^;]+);').Groups[1].Value
      min = $w; max = $w
    }
  } else {
    if ($w -lt $faces[$url].min) { $faces[$url].min = $w }
    if ($w -gt $faces[$url].max) { $faces[$url].max = $w }
  }
}
$sb = [System.Text.StringBuilder]::new()
foreach ($url in $faces.Keys) {
  $f = $faces[$url]
  $bytes = (Invoke-WebRequest -UseBasicParsing $url).Content
  $b64 = [Convert]::ToBase64String($bytes)
  [void]$sb.Append("@font-face{font-family:'$($f.family)';font-style:normal;font-weight:$($f.min) $($f.max);font-display:swap;src:url(data:font/woff2;base64,$b64) format('woff2');unicode-range:$($f.range);}`n")
}
[System.IO.File]::WriteAllText((Join-Path $dir 'fonts-inline.css'), $sb.ToString(), [System.Text.UTF8Encoding]::new($false))
Write-Host "tlock.js and fonts-inline.css ready ($($faces.Count) font files)"
