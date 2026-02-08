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
python downloader.py xrdp --dry-run
```

## Usage

```bash
python downloader.py xrdp
```

Override repositories:

```bash
python downloader.py xrdp \
    --rpm-repo https://example.org/rpm/os/x86_64/ \
    --deb-repo http://example.org/debian/dists/bullseye/main/binary-amd64/
```

Skip RPM or DEB processing:

```bash
python downloader.py xrdp --no-deb
python downloader.py xrdp --no-rpm
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

## Notes

- RPM dependency resolution uses `python-solv`.
- RPM repodata compression can be `.gz`, `.xz`, or `.zst` (requires `zstandard`).
- DEB dependency resolution is a simple parser for `Depends:` fields and does not handle virtual packages.
- Proxy settings rely on environment variables `HTTP_PROXY` and `HTTPS_PROXY`.
