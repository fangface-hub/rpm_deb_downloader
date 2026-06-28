Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $repoRoot

$originalPythonPath = $env:PYTHONPATH
$toolsBinPath = Join-Path $repoRoot "tools\bin"
if ($originalPythonPath) {
    $env:PYTHONPATH = "$toolsBinPath;$originalPythonPath"
} else {
    $env:PYTHONPATH = $toolsBinPath
}

try {
    $python = $null
    $pythonCandidates = @(
        (Join-Path $repoRoot ".venv\Scripts\python.exe")
    )

    $pythonCommands = Get-Command python -All -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -and $_.Source -notlike "*WindowsApps*" } |
        Select-Object -ExpandProperty Source -Unique
    if ($pythonCommands) {
        $pythonCandidates += $pythonCommands
    }

    foreach ($candidate in $pythonCandidates) {
        if (-not $candidate -or -not (Test-Path $candidate)) {
            continue
        }

        & $candidate --version *> $null
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    }

    if (-not $python) {
        throw "No usable Python was found. Recreate .venv or add python.org Python to PATH."
    }

    $clang = Get-Command clang-cl -ErrorAction SilentlyContinue
    if (-not $clang) {
        throw "clang-cl was not found in PATH. Install LLVM/Clang for Windows."
    }

    $outputRoot = Join-Path $repoRoot "dist"
    $buildRoot = Join-Path $repoRoot "build\nuitka"
    $releaseExe = Join-Path $outputRoot "RpmDebDownloader.exe"

    if (Test-Path $buildRoot) {
        Remove-Item $buildRoot -Recurse -Force
    }
    if (Test-Path $outputRoot) {
        Remove-Item $outputRoot -Recurse -Force
    }

    New-Item -ItemType Directory -Path $buildRoot | Out-Null
    New-Item -ItemType Directory -Path $outputRoot | Out-Null

    $options = @(
        "-m",
        "nuitka",
        "--onefile",
        "--clang",
        "--lto=auto",
        "--assume-yes-for-downloads",
        "--enable-plugin=tk-inter",
        "--windows-console-mode=disable",
        "--output-dir=$buildRoot",
        "--output-filename=RpmDebDownloader.exe",
        "--include-data-dir=$repoRoot\tools=tools",
        "--include-data-dir=$repoRoot\locales=locales",
        "--include-data-dir=$repoRoot\Licenses=Licenses",
        "--include-data-file=$repoRoot\pyproject.toml=pyproject.toml",
        "--remove-output",
        "$repoRoot\main_window.py"
    )

    & $python $options
    if ($LASTEXITCODE -ne 0) {
        throw "Nuitka build failed with exit code $LASTEXITCODE"
    }

    $onefileExe = Join-Path $buildRoot "main_window.onefile.exe"
    if (-not (Test-Path $onefileExe)) {
        $onefileExe = Join-Path $buildRoot "RpmDebDownloader.exe"
    }

    if (-not (Test-Path $onefileExe)) {
        throw "Nuitka onefile output exe was not found."
    }

    Move-Item $onefileExe $releaseExe

    Copy-Item (Join-Path $repoRoot "tools") (Join-Path $outputRoot "tools") -Recurse -Force
    Copy-Item (Join-Path $repoRoot "locales") (Join-Path $outputRoot "locales") -Recurse -Force
    Copy-Item (Join-Path $repoRoot "Licenses") (Join-Path $outputRoot "Licenses") -Recurse -Force
    Copy-Item (Join-Path $repoRoot "pyproject.toml") (Join-Path $outputRoot "pyproject.toml") -Force

    $packagedSolvPy = Join-Path $outputRoot "tools\bin\solv.py"
    if (Test-Path $packagedSolvPy) {
        Remove-Item $packagedSolvPy -Force
    }

    $requiredPaths = @(
        $releaseExe,
        (Join-Path $outputRoot "tools\bin\solv.dll"),
        (Join-Path $outputRoot "tools\bin\solvext.dll"),
        (Join-Path $outputRoot "tools\bin\rpmmd2solv.exe"),
        (Join-Path $outputRoot "locales\ja.json"),
        (Join-Path $outputRoot "pyproject.toml")
    )

    foreach ($path in $requiredPaths) {
        if (-not (Test-Path $path)) {
            throw "Required file is missing: $path"
        }
    }

    Write-Host "Nuitka build completed: $releaseExe"
}
finally {
    $env:PYTHONPATH = $originalPythonPath
    Pop-Location
}