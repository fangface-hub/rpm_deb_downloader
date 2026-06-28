# rpm_deb_downloader

Resolve RPM and DEB dependencies and download packages on Windows using Python and libsolv.

## Setup

1. Create a virtual environment and install dependencies:

```bash
uv sync
```

1. Run a dry run first:

```bash
uv run python .\main_window.py
```

## Usage

```bash
uv run python .\main_window.py
```

Windows では既定のデータディレクトリとして `%USERPROFILE%\Documents\RpmDebDownloader` を使います。
初回起動時は確認ダイアログが表示され、別のフォルダを選んだ場合はそのパスが `settings.json` に保存され、次回起動からそのフォルダが使われます。

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

## Build release with Nuitka

PyInstaller の代わりに Nuitka を使って Windows 向けの配布物を生成します。
このリポジトリでは onefile ビルドを前提にしています。

### Release prerequisites

- Python from python.org (x64) 3.14
- LLVM/Clang for Windows (`clang-cl` in `PATH`)
- Visual Studio Build Tools 2022 (MSVC linker + Windows SDK)

### Build setup

```powershell
uv sync --extra build
```

### Build command

```powershell
powershell -ExecutionPolicy Bypass -File .\build_nuitka.ps1
```

### Version bump scripts

バージョン更新には以下のスクリプトを使います。

- `bump_major.ps1`: メジャーを +1 し、minor/patch を 0 にリセット
- `bump_minor.ps1`: マイナーを +1 し、patch を 0 にリセット
- `bump_patch.ps1`: パッチを +1

実行例:

```powershell
.\bump_major.ps1
.\bump_minor.ps1
.\bump_patch.ps1
```

これらは `pyproject.toml` の `version = "X.Y.Z"` と、`AppxManifest.xml` の `Version="X.Y.Z.0"` を同時に更新します。

### Local test for MSIX packaging and signing

```powershell
powershell -ExecutionPolicy Bypass -File .\build_msix_local.ps1
```

Optional arguments:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_msix_local.ps1 -PublisherCN "CN=YOUR-CN" -IdentityName "YourName.RpmDebDownloader" -PublisherName "Your Name"
```

Generated files:

- `dist\RpmDebDownloader.msix`
- `dist\RpmDebDownloader.cer`

成果物は `dist\RpmDebDownloader.exe` に配置されます。
`tools/bin` の DLL/EXE、`tools/REPOS.json`、`locales/`、`Licenses/`、`pyproject.toml` は onefile exe に内包され、
実行時に展開されます。`solv.py` は配布物に含めず、exe 内に取り込みます。

### Smoke test

```powershell
.\dist\RpmDebDownloader.exe
```

### Notes for Nuitka

- RPM 機能は exe 内に取り込まれた `solv` モジュールが `ctypes` で `solv.dll` / `solvext.dll` を直接ロードします。
- `rpmmd2solv.exe` は外部プロセスとして実行されるため、`tools/bin/` ごと配布物へ含める必要があります。
- `main_window.py` は `pyproject.toml` からバージョンを読むため、Nuitka 配布物にも同梱します。

## Build libsolv artifacts on Windows with clang-cl

`python-solv` is not distributed on PyPI for Windows. Build it locally using
libsolv + SWIG and install into your venv.

### libsolv prerequisites

- Visual Studio Build Tools 2022 (MSVC linker + Windows SDK)
- LLVM/Clang for Windows (`clang-cl`, `lld-link`)
- CMake (in PATH)
- Ninja (in PATH)
- Git (in PATH)
- SWIG (in PATH)
- Python from python.org (x64) 3.14

### Build steps (PowerShell)

```powershell
# vcpkg for zlib/expat
cd C:\Users\<you>\Documents
git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
\bootstrap-vcpkg.bat
\vcpkg.exe install zlib:x64-windows expat:x64-windows

# libsolv source
cd C:\Users\<you>\Documents
git clone https://github.com/openSUSE/libsolv.git
cd libsolv

# apply Windows patches for python bindings
git apply C:\Users\<you>\Documents\rpm_deb_downloader\tools\patches\libsolv-windows.patch

# paths
$py = (uv run python -c "import sys; print(sys.executable)").Trim()
$platlib = & $py -c "import sysconfig; print(sysconfig.get_path('platlib'))"
$swig = (Get-Command swig).Source

$src = "C:\Users\<you>\Documents\libsolv"
$build = "C:\Users\<you>\Documents\libsolv-build"
$install = "C:\Users\<you>\Documents\libsolv-install"

cmake -S $src -B $build -G "Ninja" `
    -DCMAKE_INSTALL_PREFIX=$install `
    -DCMAKE_PREFIX_PATH=C:\Users\<you>\Documents\vcpkg\installed\x64-windows `
    -DCMAKE_C_COMPILER=clang-cl `
    -DCMAKE_CXX_COMPILER=clang-cl `
    -DCMAKE_LINKER=lld-link `
    -DCMAKE_BUILD_TYPE=Release `
    -DWITHOUT_COOKIEOPEN=ON -DENABLE_PYTHON=ON `
    -DSWIG_EXECUTABLE=$swig `
    -DPYTHON_EXECUTABLE=$py `
    -DPYTHON_LIBRARY=C:\Python314\libs\python314.lib `
    -DPYTHON_INCLUDE_DIR=C:\Python314\include

cmake --build $build
cmake --install $build

# install the extension into the venv
Copy-Item "$install\bin\solv.dll" $platlib -Force
Copy-Item "$install\bin\solvext.dll" $platlib -Force
Copy-Item "C:\Users\<you>\Documents\vcpkg\installed\x64-windows\bin\libexpat.dll" $platlib -Force
Copy-Item "C:\Users\<you>\Documents\vcpkg\installed\x64-windows\bin\zlib1.dll" $platlib -Force
Copy-Item "$platlib\solv.py" "C:\Users\<you>\Documents\rpm_deb_downloader\tools\bin\solv.py" -Force

# make rpmmd2solv available to the app (fallback when bindings lack add_rpmmd)
Copy-Item "$install\bin\rpmmd2solv.exe" "C:\Users\<you>\Documents\rpm_deb_downloader\tools\bin\rpmmd2solv.exe" -Force
Copy-Item "$install\bin\solv.dll" "C:\Users\<you>\Documents\rpm_deb_downloader\tools\bin\solv.dll" -Force
Copy-Item "$install\bin\solvext.dll" "C:\Users\<you>\Documents\rpm_deb_downloader\tools\bin\solvext.dll" -Force
Copy-Item "C:\Users\<you>\Documents\vcpkg\installed\x64-windows\bin\libexpat.dll" "C:\Users\<you>\Documents\rpm_deb_downloader\tools\bin\libexpat.dll" -Force
Copy-Item "C:\Users\<you>\Documents\vcpkg\installed\x64-windows\bin\zlib1.dll" "C:\Users\<you>\Documents\rpm_deb_downloader\tools\bin\zlib1.dll" -Force
```

`clang-cl` を使う理由は、Windows で MSVC ABI を維持したまま LLVM 系コンパイラへ寄せるためです。
MinGW 系 clang へ切り替えると、CRT や依存 DLL の整合性確認コストが上がります。

Verify:

```powershell
$py -c "import solv; print(solv)"
```

### Bundled build artifacts in this repository

This repository already includes Windows build artifacts under `tools/`, so other
developers can run the app without rebuilding libsolv immediately.

`tools/bin/*` は Git LFS 管理です。CI では `actions/checkout` に
`with: lfs: true` を設定し、ローカル clone でも `git lfs pull` を実行して
実体ファイルを取得してください（LFS未取得だと `solv.py` がポインタテキストになり実行時に失敗します）。

- `tools/bin/rpmmd2solv.exe`
- `tools/bin/solv.dll`
- `tools/bin/solvext.dll`
- `tools/bin/solv.py` (`ctypes` で `solv.dll` / `solvext.dll` を直接呼び出す)
- `tools/bin/libexpat.dll`
- `tools/bin/zlib1.dll`
- `tools/patches/libsolv-windows.patch` (patch used for the Windows build)

このアプリでは `_solv.pyd` / `_solv.dll` は不要です。RPM の依存解決は
`tools/bin/solv.py` から `solv.dll` と `solvext.dll` を直接読み込みます。

### Updating bundled artifacts

When updating these binaries, keep source/version information in the commit
message and PR description so others can reproduce the build later.

Recommended metadata to record:

- libsolv source revision (tag or commit SHA)
- SWIG version
- Python version and architecture (for example `3.14 x64`)
- vcpkg revision and `zlib`/`expat` package versions

Minimal update workflow:

1. Rebuild with the steps above using the target Python version.
1. Replace files in `tools/bin/` with the newly built binaries.
1. Run a smoke test: `uv run python .\main_window.py`.
1. Run import test: `uv run python -c "import solv; print(solv)"`.
1. Run Nuitka smoke test: `.\dist\RpmDebDownloader.exe`.
1. Commit binaries and documentation updates together.

## Notes

- RPM dependency resolution uses `python-solv`.
- RPM repodata compression can be `.gz`, `.xz`, or `.zst` (requires `zstandard`).
- DEB dependency resolution is a simple parser for `Depends:` fields and does not handle virtual packages.
- Proxy settings rely on environment variables `HTTP_PROXY` and `HTTPS_PROXY`.

## Sponsor

[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/fangface-hub)
