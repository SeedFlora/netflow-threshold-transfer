param([string]$Config = 'configs/main.yaml')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
function Invoke-Lab {
    & $Python -m nids_lab @args
    if ($LASTEXITCODE -ne 0) { throw "nids_lab failed: $args" }
}
Invoke-Lab doctor
Invoke-Lab audit --data 'f7546561558c07c5_NFV3DATA-A11964_A11964.zip'
Invoke-Lab prepare --config $Config
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
Invoke-Lab freeze --config $Config
Invoke-Lab smoke --config configs/smoke.yaml --resume
Invoke-Lab run --config $Config --resume
Invoke-Lab evaluate --config $Config
Invoke-Lab report --config $Config
