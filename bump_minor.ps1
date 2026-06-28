# bump_minor.ps1 - Increment minor and reset patch

$ErrorActionPreference = 'Stop'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$toml = Join-Path $root 'pyproject.toml'
$xml = Join-Path $root 'AppxManifest.xml'

$tomlContent = Get-Content $toml -Raw -Encoding UTF8
if ($tomlContent -notmatch 'version\s*=\s*"(\d+)\.(\d+)\.(\d+)"') {
    Write-Error 'Cannot read version from pyproject.toml'
    exit 1
}

$major = [int]$Matches[1]
$minor = [int]$Matches[2]
$patch = [int]$Matches[3]

$newMinor = $minor + 1
$newPatch = 0

$oldVer = ('{0}.{1}.{2}' -f $major, $minor, $patch)
$newVer = ('{0}.{1}.{2}' -f $major, $newMinor, $newPatch)
$newVerW = ('{0}.{1}.{2}.0' -f $major, $newMinor, $newPatch)

Write-Host ('Bump: ' + $oldVer + ' -> ' + $newVer)

$tomlNew = $tomlContent -replace 'version\s*=\s*"\d+\.\d+\.\d+"', ('version = "' + $newVer + '"')
[System.IO.File]::WriteAllText($toml, $tomlNew, $utf8NoBom)
Write-Host '  Updated: pyproject.toml'

$xmlContent = Get-Content $xml -Raw -Encoding UTF8
$xmlNew = $xmlContent -replace 'Version="\d+\.\d+\.\d+\.\d+"', ('Version="' + $newVerW + '"')
[System.IO.File]::WriteAllText($xml, $xmlNew, $utf8NoBom)
Write-Host '  Updated: AppxManifest.xml'

Write-Host ('Done. New version: ' + $newVer)