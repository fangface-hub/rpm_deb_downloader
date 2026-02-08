# rpm_deb_downloader

Resolve RPM and DEB dependencies and download packages on Windows using Python and libsolv.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

1. Run a dry run first:

```bash
python .\main_window.py
```

## Usage

```bash
python .\main_window.py
```

GUIでは、パッケージ入力はテキスト入力ではなくJSONファイル選択です。
`service_type` と `package_name` を持つオブジェクトの配列を指定します。

例:

```json
[
    {"service_type": "RPM", "package_name": "bash"},
    {"service_type": "RPM", "package_name": "coreutils"},
    {"service_type": "DEB", "package_name": "curl"}
]
```

## Build python-solv on Windows (MSVC)

`python-solv` is not distributed on PyPI for Windows. Build it locally using
libsolv + SWIG and install into your venv.

### Prerequisites

- Visual Studio Build Tools 2022 (C++ tools + Windows SDK)
- CMake (in PATH)
- Git (in PATH)
- SWIG (in PATH)
- Python from python.org (x64) that matches your venv version

### Build steps (PowerShell)

```powershell
# vcpkg for zlib
cd C:\Users\<you>\Documents
git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
\bootstrap-vcpkg.bat
\vcpkg.exe install zlib:x64-windows

# libsolv source
cd C:\Users\<you>\Documents
git clone https://github.com/openSUSE/libsolv.git
cd libsolv

# apply Windows patches for python bindings
git apply C:\Users\<you>\Documents\rpm_deb_downloader\tools\patches\libsolv-windows.patch

# paths
$venv = "C:\Users\<you>\Documents\rpm_deb_downloader\.venv"
$py = "$venv\Scripts\python.exe"
$platlib = & $py -c "import sysconfig; print(sysconfig.get_path('platlib'))"
$swig = (Get-Command swig).Source

$src = "C:\Users\<you>\Documents\libsolv"
$build = "C:\Users\<you>\Documents\libsolv-build"
$install = "C:\Users\<you>\Documents\libsolv-install"

cmake -S $src -B $build -G "Visual Studio 17 2022" -A x64 `
    -DCMAKE_INSTALL_PREFIX=$install `
    -DCMAKE_PREFIX_PATH=C:\Users\<you>\Documents\vcpkg\installed\x64-windows `
    -DWITHOUT_COOKIEOPEN=ON -DENABLE_PYTHON=ON `
    -DSWIG_EXECUTABLE=$swig `
    -DPYTHON_EXECUTABLE=$py `
    -DPYTHON_LIBRARY=C:\Python313\libs\python313.lib `
    -DPYTHON_INCLUDE_DIR=C:\Python313\include

cmake --build $build --config Release
cmake --install $build --config Release

# install the extension into the venv
Copy-Item "$install\bin\solv.dll" $platlib -Force
Copy-Item "$install\bin\solvext.dll" $platlib -Force
Copy-Item "C:\Users\<you>\Documents\vcpkg\installed\x64-windows\bin\libexpat.dll" $platlib -Force
Copy-Item "C:\Users\<you>\Documents\vcpkg\installed\x64-windows\bin\zlib1.dll" $platlib -Force
if (Test-Path "$platlib\_solv.dll") { Rename-Item "$platlib\_solv.dll" _solv.pyd -Force }

# make rpmmd2solv available to the app (fallback when bindings lack add_rpmmd)
Copy-Item "$install\bin\rpmmd2solv.exe" "C:\Users\<you>\Documents\rpm_deb_downloader\tools\bin\rpmmd2solv.exe" -Force
```

Verify:

```powershell
$py -c "import solv; print(solv)"
```

### Bundled build artifacts in this repository

This repository already includes Windows build artifacts under `tools/`, so other
developers can run the app without rebuilding libsolv/python-solv immediately.

`tools/bin/*` は Git LFS 管理です。CI では `actions/checkout` に
`with: lfs: true` を設定し、ローカル clone でも `git lfs pull` を実行して
実体ファイルを取得してください（LFS未取得だと `solv.py` がポインタテキストになり実行時に失敗します）。

- `tools/bin/rpmmd2solv.exe`
- `tools/bin/solv.dll`
- `tools/bin/solvext.dll`
- `tools/bin/solv.py`
- `tools/bin/_solv.pyd` (Python ABI must match bundled Python, e.g. CPython 3.13)
- `tools/bin/libexpat.dll`
- `tools/bin/zlib1.dll`
- `tools/patches/libsolv-windows.patch` (patch used for the Windows build)

### Updating bundled artifacts

When updating these binaries, keep source/version information in the commit
message and PR description so others can reproduce the build later.

Recommended metadata to record:

- libsolv source revision (tag or commit SHA)
- SWIG version
- Python version and architecture (for example `3.13 x64`)
- vcpkg revision and `zlib`/`expat` package versions

Minimal update workflow:

1. Rebuild with the steps above using the target Python version.
1. Replace files in `tools/bin/` with the newly built binaries.
1. Run a smoke test: `python .\main_window.py`.
1. Run import test: `python -c "import solv; print(solv)"`.
1. Commit binaries and documentation updates together.

## Notes

- RPM dependency resolution uses `python-solv`.
- RPM repodata compression can be `.gz`, `.xz`, or `.zst` (requires `zstandard`).
- DEB dependency resolution is a simple parser for `Depends:` fields and does not handle virtual packages.
- Proxy settings rely on environment variables `HTTP_PROXY` and `HTTPS_PROXY`.
