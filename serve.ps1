# Minimal static server for previewing lastkey.html locally (no Node/Python needed).
$root = $PSScriptRoot
$l = [System.Net.HttpListener]::new()
$l.Prefixes.Add('http://localhost:8765/')
$l.Start()
Write-Host 'Serving on http://localhost:8765/'
while ($l.IsListening) {
  $ctx = $l.GetContext()
  $name = $ctx.Request.Url.AbsolutePath.TrimStart('/')
  if (-not $name) { $name = 'lastkey.html' }
  $path = Join-Path $root $name
  if (Test-Path $path -PathType Leaf) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ($name -eq 'lastkey.html') {
      $prefix = [System.Text.Encoding]::UTF8.GetBytes("<!doctype html><html lang=`"en`"><head><meta charset=`"utf-8`"><meta name=`"viewport`" content=`"width=device-width, initial-scale=1, viewport-fit=cover`"><style>[hidden]{display:none!important}body{margin:0}</style></head><body>")
      $bytes = $prefix + $bytes
    }
    if ($name -like '*.html') { $ctx.Response.ContentType = 'text/html; charset=utf-8' }
    $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
  } else { $ctx.Response.StatusCode = 404 }
  $ctx.Response.Close()
}
