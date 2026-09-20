$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install.py'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $installer @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $installer @args
} else {
    throw 'Python 3.11 or newer is required. No configuration was changed.'
}
exit $LASTEXITCODE
