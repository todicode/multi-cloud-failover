# Dot-source this file in EACH PowerShell window used for the local lab.
# It changes only this terminal's environment and working directory.
$labRepositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $labRepositoryRoot

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:LOCAL_REPL_PROJECT = 'mcf-todicode'
$env:AWS_DB_PORT = '56432'
$env:AZURE_DB_PORT = '56433'
$env:AWS_WEB_PORT = '8180'
$env:AZURE_WEB_PORT = '8181'
$env:PROXY_WEB_PORT = '8190'
$env:LOCAL_REPL_DB_ONLY = '0'
# Demo-only password: the database port is bound to localhost by Compose.
$env:DATABASE_URL = 'postgresql://taskflow:local-demo-only@127.0.0.1:56432/taskflow'

$LocalLabUrl = 'http://127.0.0.1:8190'
$LocalLabAwsUrl = 'http://127.0.0.1:8180'
$LocalLabAzureUrl = 'http://127.0.0.1:8181'

Write-Host 'Local lab: mcf-todicode (separate Docker project and ports)'
Write-Host "Shared: $LocalLabUrl/issues.html"
Write-Host "AWS:    $LocalLabAwsUrl/issues.html | PostgreSQL: 56432"
Write-Host "Azure:  $LocalLabAzureUrl/issues.html | PostgreSQL: 56433"
