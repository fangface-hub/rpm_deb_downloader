#!python3
"""Path utilities for application and data directories."""

import json
import os
import platform
import sys
from pathlib import Path


def ensure_trailing_slash(url: str) -> str:
    """Ensure the URL ends with a slash.

    Parameters
    ----------
    url : str
        The URL to check and modify if necessary.
    Returns
    -------
    str
        The URL guaranteed to end with a slash.
    """
    return url if url.endswith("/") else url + "/"


def get_app_dir() -> Path:
    """アプリケーションのルートディレクトリを取得.

    Get application root directory.

    PyInstaller/Nuitkaなどでビルドされた場合は実行ファイルの
    ディレクトリ、開発環境ではスクリプトのディレクトリを返します。

    Returns
    -------
    Path
        アプリケーションのルートディレクトリ
    """
    # 実行時に起動したパスを最優先で確認（Nuitka onefile対策）
    if sys.argv and sys.argv[0]:
        launch_path = Path(sys.argv[0]).resolve()
        if launch_path.suffix.lower() == ".exe":
            return launch_path.parent

    if '__compiled__' in globals():
        # Nuitka standalone / onefile フォールバック
        return Path(sys.executable).resolve().parent
    if getattr(sys, 'frozen', False):
        # PyInstallerでビルドされた場合
        return Path(sys.executable).parent
    else:
        # 通常のPythonスクリプトとして実行される場合
        return Path(__file__).parent


def get_default_data_dir() -> Path:
    """既定のデータディレクトリを取得する."""
    if platform.system() == "Windows":
        userprofile = os.getenv("USERPROFILE")
        if userprofile:
            return Path(userprofile) / "Documents" / "RpmDebDownloader"
        return Path.home() / "Documents" / "RpmDebDownloader"

    if platform.system() == "Darwin":
        return (Path.home() / "Library" / "Application Support" /
                "RpmDebDownloader")

    return (Path(os.getenv("XDG_DATA_HOME",
                           Path.home() / ".local" / "share")) /
            "RpmDebDownloader")


def get_legacy_data_dir() -> Path:
    """旧Windows既定のデータディレクトリを取得する."""
    if platform.system() == "Windows":
        return (Path(os.getenv("LOCALAPPDATA", os.path.expanduser("~"))) /
                "RpmDebDownloader")
    return get_default_data_dir()


def get_settings_file_path() -> Path:
    """設定ファイルの固定保存先を取得する."""
    return get_default_data_dir() / "settings.json"


def get_existing_settings_file_path() -> Path:
    """存在する設定ファイルを取得する."""
    settings_file = get_settings_file_path()
    if settings_file.exists():
        return settings_file

    legacy_settings = get_legacy_data_dir() / "settings.json"
    if legacy_settings.exists():
        return legacy_settings

    return settings_file


def get_data_dir() -> Path:
    """データディレクトリを取得 / Get data directory.

    プラットフォームごとに適切な場所を返します。
    Returns appropriate location for each platform:
    - Windows: %USERPROFILE%\\Documents\\RpmDebDownloader
    - macOS: ~/Library/Application Support/RpmDebDownloader
    - Linux: ~/.local/share/RpmDebDownloader (XDG Base Directory)

    Returns
    -------
    Path
        データディレクトリ / Data directory path
    """
    if platform.system() == "Windows":
        settings_file = get_settings_file_path()
        if settings_file.exists():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                data_dir = settings.get("data_dir")
                if isinstance(data_dir, str) and data_dir.strip():
                    return Path(data_dir.strip())
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        return get_default_data_dir()

    return get_default_data_dir()


def get_documents_dir() -> Path:
    """ドキュメントディレクトリを取得 / Get documents directory.

    プラットフォームごとに一般的なドキュメントフォルダのパスを返します。
    Returns typical documents directory for each platform:
    - Windows: OneDrive Documents (if available) or %USERPROFILE%\\Documents
    - macOS: ~/Documents
    - Linux and others: ~/Documents

    Returns
    -------
    Path
        ドキュメントディレクトリ / Documents directory path
    """
    if platform.system() == "Windows":
        onedrive = os.getenv("OneDrive")
        if onedrive:
            onedrive_docs = Path(onedrive) / "Documents"
            if onedrive_docs.exists():
                return onedrive_docs

        userprofile = os.getenv("USERPROFILE")
        if userprofile:
            return Path(userprofile) / "Documents"

    return Path.home() / "Documents"


def get_initial_dir_and_file(current_path: str,
                             fallback_dir: str = "") -> tuple[str, str]:
    """current_pathからinitial_dirとinitial_fileを判定.

    Parameters
    ----------
    current_path : str
        現在のパス（ファイルまたはディレクトリ）
    fallback_dir : str, optional
        パスが存在しない場合のフォールバックディレクトリ, by default ""

    Returns
    -------
    tuple[str, str]
        (initial_dir, initial_file) のタプル
    """
    if os.path.isfile(current_path):
        initial_dir = os.path.dirname(current_path)
        initial_file = os.path.basename(current_path)
    elif os.path.isdir(current_path):
        initial_dir = current_path
        initial_file = ""
    else:
        # パスが存在しない場合はフォールバックディレクトリを使用
        initial_dir = fallback_dir
        initial_file = ""

    return initial_dir, initial_file
