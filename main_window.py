#!/usr/bin/env python3
"""メインウィンドウの実装."""
import base64
import importlib
import json
import logging
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
import tomllib
import traceback
from tkinter import filedialog, messagebox
from urllib.parse import quote

from downloader import run
from i18n import I18n
from package_json_editor_window import PackageJsonEditorWindow
from package_service import PackageRequest, ServiceRepo, ServiceType
from pathlibex import get_app_dir, get_data_dir, get_documents_dir
from proxy_settings_dialog import ProxySettingsDialog
from repo_json_editor_window import RepoJsonEditorWindow
from tkinterex import CustomCheckbutton, CustomCombobox, CustomEntry


class ProxyEnvironmentManager:
    """プロキシ環境変数を管理するクラス."""

    def __init__(self):
        """元の環境変数を保存."""
        self.original_http_proxy = os.environ.get("HTTP_PROXY")
        self.original_https_proxy = os.environ.get("HTTPS_PROXY")
        self.original_http_proxy_lower = os.environ.get("http_proxy")
        self.original_https_proxy_lower = os.environ.get("https_proxy")

    def set_proxy(self,
                  use_proxy: bool,
                  url: str,
                  username: str = "",
                  password: str = "") -> None:
        """プロキシ環境変数を設定."""
        if use_proxy and url:
            proxy_url = url
            if username and password:
                encoded_username = quote(username, safe="")
                encoded_password = quote(password, safe="")
                scheme, host = (proxy_url.split("://", 1)
                                if "://" in proxy_url else ("http", proxy_url))
                proxy_url = (
                    f"{scheme}://{encoded_username}:{encoded_password}@{host}")

            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ["http_proxy"] = proxy_url
            os.environ["https_proxy"] = proxy_url
        else:
            self.clear_proxy()

    def restore_proxy(self) -> None:
        """元の環境変数に復元."""
        if self.original_http_proxy:
            os.environ["HTTP_PROXY"] = self.original_http_proxy
        elif "HTTP_PROXY" in os.environ:
            del os.environ["HTTP_PROXY"]

        if self.original_https_proxy:
            os.environ["HTTPS_PROXY"] = self.original_https_proxy
        elif "HTTPS_PROXY" in os.environ:
            del os.environ["HTTPS_PROXY"]

        if self.original_http_proxy_lower:
            os.environ["http_proxy"] = self.original_http_proxy_lower
        elif "http_proxy" in os.environ:
            del os.environ["http_proxy"]

        if self.original_https_proxy_lower:
            os.environ["https_proxy"] = self.original_https_proxy_lower
        elif "https_proxy" in os.environ:
            del os.environ["https_proxy"]

    def clear_proxy(self) -> None:
        """プロキシ環境変数をクリア."""
        for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            if key in os.environ:
                del os.environ[key]


class _TeeStream:
    """元のストリームへ出力しつつ、GUIにも転送するストリーム."""

    def __init__(self, original_stream, forward_callback):
        self._original_stream = original_stream
        self._forward_callback = forward_callback

    def write(self, data: str) -> int:
        if not data:
            return 0
        if self._original_stream and hasattr(self._original_stream, "write"):
            self._original_stream.write(data)
        self._forward_callback(data)
        return len(data)

    def flush(self) -> None:
        if self._original_stream and hasattr(self._original_stream, "flush"):
            self._original_stream.flush()


class StreamCaptureManager:
    """標準出力・標準エラー出力を一時的に捕捉するマネージャ."""

    def __init__(self, stdout_callback, stderr_callback):
        self._stdout_callback = stdout_callback
        self._stderr_callback = stderr_callback
        self._original_stdout = None
        self._original_stderr = None
        self._restore_stdout = None
        self._restore_stderr = None
        self._active = False
        self._patched_handlers = []

    def start(self) -> None:
        """捕捉を開始する."""
        if self._active:
            return

        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._restore_stdout = (self._original_stdout if self._original_stdout
                                is not None else sys.__stdout__)
        self._restore_stderr = (self._original_stderr if self._original_stderr
                                is not None else sys.__stderr__)
        sys.stdout = _TeeStream(self._original_stdout, self._stdout_callback)
        sys.stderr = _TeeStream(self._original_stderr, self._stderr_callback)

        self._patched_handlers.clear()
        for logger in self._iter_loggers():
            for handler in logger.handlers:
                if not isinstance(handler, logging.StreamHandler):
                    continue
                if handler.stream is self._original_stdout:
                    self._patched_handlers.append(
                        (handler, self._restore_stdout))
                    handler.setStream(sys.stdout)
                elif handler.stream is self._original_stderr:
                    self._patched_handlers.append(
                        (handler, self._restore_stderr))
                    handler.setStream(sys.stderr)

        self._active = True

    def stop(self) -> None:
        """捕捉を終了して元に戻す."""
        if not self._active:
            return

        for handler, stream in self._patched_handlers:
            handler.setStream(stream)
        self._patched_handlers.clear()

        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        self._original_stdout = None
        self._original_stderr = None
        self._restore_stdout = None
        self._restore_stderr = None
        self._active = False

    def _iter_loggers(self):
        """有効なロガーを列挙する."""
        yield logging.getLogger()
        for value in logging.Logger.manager.loggerDict.values():
            if isinstance(value, logging.Logger):
                yield value


class LogOutputDialog(tk.Toplevel):
    """標準出力・標準エラー出力を表示するモードレスダイアログ."""

    def __init__(self, master, on_close, i18n: I18n):
        super().__init__(master)
        self.i18n = i18n
        self.title(self.i18n.t("log_output_title"))
        self.geometry("900x420")
        self._on_close = on_close
        self._queue = queue.Queue()

        self.text = tk.Text(self, wrap="none")
        self.text.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.text.tag_configure("stderr", foreground="#c62828")

        button_frame = tk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=10)
        self.clear_button = tk.Button(button_frame,
                                      text=self.i18n.t("clear"),
                                      command=self.clear)
        self.clear_button.pack(side="left")
        self.close_button = tk.Button(button_frame,
                                      text=self.i18n.t("close"),
                                      command=self._close)
        self.close_button.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._drain_queue)

    def append_stdout(self, text: str) -> None:
        """標準出力を追加する."""
        self._queue.put(("stdout", text))

    def append_stderr(self, text: str) -> None:
        """標準エラー出力を追加する."""
        self._queue.put(("stderr", text))

    def clear(self) -> None:
        """表示内容をクリアする."""
        self.text.delete("1.0", tk.END)

    def _drain_queue(self) -> None:
        """キューの内容をテキストへ反映する."""
        try:
            while True:
                stream_type, payload = self._queue.get_nowait()
                if stream_type == "stderr":
                    self.text.insert(tk.END, payload, "stderr")
                else:
                    self.text.insert(tk.END, payload)
        except queue.Empty:
            pass

        self.text.see(tk.END)
        if self.winfo_exists():
            self.after(80, self._drain_queue)

    def _close(self) -> None:
        """ウィンドウを閉じる."""
        if self._on_close:
            self._on_close()
        self.destroy()


class LocaleSettingsDialog(tk.Toplevel):
    """ロケール選択ダイアログ（モードレス）."""

    def __init__(self, parent, main_gui):
        super().__init__(parent)
        self.main_gui = main_gui
        self.i18n = main_gui.i18n
        self.title(self.i18n.t("locale_settings"))
        self.geometry("360x140")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        container = tk.Frame(self)
        container.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(container,
                 text=self.i18n.t("select_language")).pack(anchor="w")

        self.language_map = {
            f"{lang['code']} - {lang['name']}": lang["code"]
            for lang in self.i18n.get_available_languages()
        }
        values = list(self.language_map.keys())
        self.language_combo = CustomCombobox(container,
                                             values=values,
                                             state="readonly",
                                             width=30)
        current = self.i18n.get_current_language()
        selected = next(
            (label
             for label, code in self.language_map.items() if code == current),
            "")
        self.language_combo.value = selected
        self.language_combo.pack(anchor="w", pady=(6, 10))

        button_frame = tk.Frame(container)
        button_frame.pack(fill="x")
        tk.Button(button_frame, text=self.i18n.t("ok"),
                  command=self._on_ok).pack(side="left")
        tk.Button(button_frame,
                  text=self.i18n.t("cancel"),
                  command=self.destroy).pack(side="left", padx=6)

    def _on_ok(self) -> None:
        """選択した言語を適用して保存する."""
        selected_label = self.language_combo.value
        selected_code = self.language_map.get(selected_label)
        if not selected_code:
            self.destroy()
            return

        self.main_gui.i18n.change_language(selected_code)
        self.main_gui.save_settings(show_message=False)
        messagebox.showinfo(self.main_gui.i18n.t("info"),
                            self.main_gui.i18n.t("restart_required"))
        self.destroy()


class MainWindow(tk.Tk):
    """メインウィンドウクラス."""

    def __init__(self):
        super().__init__()
        self.i18n = I18n(lang=self._load_saved_locale())
        self.root = self
        self.title(self.i18n.t("app_title"))
        self.geometry("600x200")
        self.create_menu()
        # パッケージ名
        self.package_file_path = ""
        package_frame = tk.Frame(self)
        package_frame.pack(pady=5, anchor="w")
        self.package_file_label = tk.Label(
            package_frame,
            text=self.i18n.t("package_list_not_selected"),
        )
        self.package_file_label.pack(side="left")
        self.package_file_btn = tk.Button(
            package_frame,
            text=self.i18n.t("select_existing_file"),
            command=self.select_package_file,
        )
        self.package_file_btn.pack(side="left", padx=5)
        self.package_new_btn = tk.Button(
            package_frame,
            text=self.i18n.t("create_new"),
            command=self.create_new_package_file,
        )
        self.package_new_btn.pack(side="left", padx=5)
        self.package_edit_btn = tk.Button(
            package_frame,
            text=self.i18n.t("edit"),
            command=self.open_package_editor,
        )
        self.package_edit_btn.pack(side="left", padx=5)
        self.package_edit_btn.config(state=tk.DISABLED)

        # 出力先ディレクトリ
        out_frame = tk.Frame(self)
        out_frame.pack(pady=5, anchor="w")
        self.out_entry = CustomEntry(out_frame)
        self.out_entry.value = ""
        self.out_label = tk.Label(out_frame, text=self.i18n.t("output_dir"))
        self.out_label.pack(side="left")
        self.out_entry.pack_forget()  # Entry自体は非表示に
        self.out_dir_btn = tk.Button(out_frame,
                                     text=self.i18n.t("select_output_dir"),
                                     command=self.select_output_dir)
        self.out_dir_btn.pack(side="left", padx=5)
        self.out_label.config(text=self.i18n.t("output_dir"))

        # アーキテクチャ
        arch_frame = tk.Frame(self)
        arch_frame.pack(pady=5, anchor="w")
        self.arch_label = tk.Label(arch_frame, text=self.i18n.t("architecture"))
        self.arch_label.pack(side="left")
        self.arch_combobox = CustomCombobox(
            arch_frame,
            values=["", "x86_64", "aarch64", "noarch", "i686"],
            state="readonly",
            width=16,
        )
        self.arch_combobox.value = ""
        self.arch_combobox.pack(side="left", padx=5)

        # 実行ボタン（最後に追加）
        self.run_button = tk.Button(
            self,
            text=self.i18n.t("run"),
            command=self.on_run,
        )
        self.run_button.pack(side="bottom", pady=20)

        # REPOS.jsonファイル選択
        self.repo_file_path = self.ensure_default_repo_file()
        repo_frame = tk.Frame(self)
        repo_frame.pack(pady=5, anchor="w")
        self.repo_file_label = tk.Label(
            repo_frame,
            text=self.i18n.t("repo_file_label",
                             name=os.path.basename(self.repo_file_path)))
        self.repo_file_label.pack(side="left")
        self.repo_file_btn = tk.Button(repo_frame,
                                       text=self.i18n.t("select_existing_file"),
                                       command=self.select_repo_file)
        self.repo_file_btn.pack(side="left", padx=5)
        self.repo_new_btn = tk.Button(
            repo_frame,
            text=self.i18n.t("create_new"),
            command=self.create_new_repo_file,
        )
        self.repo_new_btn.pack(side="left", padx=5)
        self.repo_edit_btn = tk.Button(
            repo_frame,
            text=self.i18n.t("edit"),
            command=self.open_repo_editor,
        )
        self.repo_edit_btn.pack(side="left", padx=5)

        self.repo_editor_window: RepoJsonEditorWindow | None = None
        self.package_editor_window: PackageJsonEditorWindow | None = None
        self.log_output_window: LogOutputDialog | None = None
        self.locale_settings_window: LocaleSettingsDialog | None = None
        self._last_output_dir: str | None = None
        self._last_repo_new_dir: str | None = None
        self._last_package_file_dir: str | None = None
        self._stream_capture = StreamCaptureManager(self._append_stdout,
                                                    self._append_stderr)

        # プロキシ設定用メンバー（ダイアログで利用）
        self.proxy_manager = ProxyEnvironmentManager()
        self.use_proxy_checkbox = CustomCheckbutton(self, text="(dummy)")
        self.use_proxy_checkbox.value = False
        self.proxy_url_entry = CustomEntry(self)
        self.proxy_username_entry = CustomEntry(self)
        self.proxy_password_entry = CustomEntry(self, show="*")
        self.load_settings()
        self.toggle_proxy_fields()

        self.arch_combobox.var.trace_add(
            "write", lambda *_: self.update_run_button_state())
        self.update_run_button_state()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def ensure_default_repo_file(self) -> str:
        """初回起動時に tools/REPOS.json を DATA_DIR へコピーして返す."""
        data_repo_path = get_data_dir() / "REPOS.json"
        if data_repo_path.exists():
            return str(data_repo_path)

        source_repo_path = get_app_dir() / "tools" / "REPOS.json"
        if source_repo_path.exists():
            data_repo_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_repo_path, data_repo_path)

        return str(data_repo_path)

    def _load_saved_locale(self) -> str | None:
        """保存済みロケールを設定ファイルから読み込む."""
        settings_file = get_data_dir() / "settings.json"
        if not settings_file.exists():
            return None

        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        value = settings.get("locale")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def create_menu(self) -> None:
        """メニューバーを作成."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        settings_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label=self.i18n.t("settings"), menu=settings_menu)
        settings_menu.add_command(label=self.i18n.t("proxy_settings"),
                                  command=self.open_proxy_settings)
        settings_menu.add_separator()
        settings_menu.add_command(
            label=self.i18n.t("save_settings"),
            command=self.save_settings,
        )
        settings_menu.add_command(label=self.i18n.t("locale_settings"),
                                  command=self.open_locale_settings)
        settings_menu.add_command(label=self.i18n.t("show_log_output"),
                                  command=self.open_log_output_window)

        help_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label=self.i18n.t("help"), menu=help_menu)
        help_menu.add_command(label=self.i18n.t("about"),
                              command=self.show_about_dialog)

    def _get_version(self) -> str:
        """pyproject.toml からバージョンを取得する."""
        pyproject_path = get_app_dir() / "pyproject.toml"
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            return data["project"]["version"]
        except (OSError, KeyError):
            return "不明"

    def show_about_dialog(self) -> None:
        """アバウトダイアログを表示する."""
        version = self._get_version()
        messagebox.showinfo(
            self.i18n.t("about_title"),
            f"RPM/DEB Downloader\n\n{self.i18n.t('version_label')}: {version}",
        )

    def open_proxy_settings(self) -> None:
        """プロキシ設定ダイアログを開く."""
        ProxySettingsDialog(self.root, self)

    def open_locale_settings(self) -> None:
        """ロケール設定ダイアログを開く."""
        if (self.locale_settings_window
                and self.locale_settings_window.winfo_exists()):
            self.locale_settings_window.lift()
            self.locale_settings_window.focus_force()
            return

        self.locale_settings_window = LocaleSettingsDialog(self.root, self)

    def open_log_output_window(self) -> None:
        """ログ出力ダイアログを開く（モードレス）."""
        if self.log_output_window and self.log_output_window.winfo_exists():
            self.log_output_window.lift()
            self.log_output_window.focus_force()
            return

        self.log_output_window = LogOutputDialog(
            self,
            on_close=self._on_log_window_close,
            i18n=self.i18n,
        )

    def _on_log_window_close(self) -> None:
        """ログ出力ダイアログ終了時の後処理."""
        self.log_output_window = None

    def _append_stdout(self, text: str) -> None:
        """stdoutテキストをログダイアログへ追記する."""
        if self.log_output_window and self.log_output_window.winfo_exists():
            self.log_output_window.append_stdout(text)

    def _append_stderr(self, text: str) -> None:
        """stderrテキストをログダイアログへ追記する."""
        if self.log_output_window and self.log_output_window.winfo_exists():
            self.log_output_window.append_stderr(text)

    def on_close(self) -> None:
        """終了時に標準出力・標準エラーの差し替えを戻して終了する."""
        self._stream_capture.stop()
        self.destroy()

    def _show_run_result_dialog(self, error: Exception | None) -> None:
        """実行完了ダイアログを表示する."""
        if error is None:
            messagebox.showinfo(self.i18n.t("completed"),
                                self.i18n.t("download_completed"))
            return
        messagebox.showerror(self.i18n.t("error"),
                             self.i18n.t("download_failed", error=error))

    def toggle_proxy_fields(self) -> None:
        """プロキシ入力欄の有効/無効を切り替える（ダイアログ連携用）."""
        state = tk.NORMAL if self.use_proxy_checkbox.value else tk.DISABLED
        self.proxy_url_entry.config(state=state)
        self.proxy_username_entry.config(state=state)
        self.proxy_password_entry.config(state=state)

    def _get_encryption_key(self) -> bytes:
        """暗号化キーを取得または生成する."""
        key_file = get_data_dir() / "encryption.key"
        if key_file.exists():
            with open(key_file, "rb") as f:
                return f.read()

        key_file.parent.mkdir(parents=True, exist_ok=True)
        fernet_class = self._get_fernet_class()
        key = fernet_class.generate_key()
        with open(key_file, "wb") as f:
            f.write(key)
        return key

    def _get_fernet_class(self):
        """Fernet クラスを動的に取得する."""
        module = importlib.import_module("cryptography.fernet")
        return module.Fernet

    def _encrypt_password(self, password: str) -> str:
        """パスワードを暗号化して文字列で返す."""
        if not password:
            return ""
        key = self._get_encryption_key()
        fernet_class = self._get_fernet_class()
        fernet = fernet_class(key)
        encrypted = fernet.encrypt(password.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def _decrypt_password(self, encrypted_password: str) -> str:
        """暗号化パスワードを復号化して返す."""
        if not encrypted_password:
            return ""
        try:
            key = self._get_encryption_key()
            fernet_class = self._get_fernet_class()
            fernet = fernet_class(key)
            encoded = encrypted_password.encode("utf-8")
            encrypted_bytes = base64.b64decode(encoded)
            decrypted = fernet.decrypt(encrypted_bytes)
            return decrypted.decode("utf-8")
        except (ImportError, ValueError, TypeError, UnicodeDecodeError):
            return ""

    def save_settings(self, show_message: bool = True) -> None:
        """設定を設定ファイルへ保存する."""
        encrypted_password = self._encrypt_password(
            self.proxy_password_entry.value, )
        settings = {
            "use_proxy": self.use_proxy_checkbox.value,
            "proxy_url": self.proxy_url_entry.value,
            "proxy_username": self.proxy_username_entry.value,
            "proxy_password_encrypted": encrypted_password,
            "locale": self.i18n.get_current_language(),
        }
        settings_file = get_data_dir() / "settings.json"
        try:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            if show_message:
                messagebox.showinfo(
                    self.i18n.t("success"),
                    self.i18n.t("settings_saved", path=settings_file),
                )
        except OSError as e:
            messagebox.showerror(self.i18n.t("error"),
                                 self.i18n.t("settings_save_failed", error=e))

    def load_settings(self) -> None:
        """設定ファイルから設定を読み込む."""
        settings_file = get_data_dir() / "settings.json"
        if not settings_file.exists():
            return

        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        if "use_proxy" in settings:
            self.use_proxy_checkbox.value = settings["use_proxy"]
        if "proxy_url" in settings:
            self.proxy_url_entry.value = settings["proxy_url"]
        if "proxy_username" in settings:
            self.proxy_username_entry.value = settings["proxy_username"]
        if "proxy_password_encrypted" in settings:
            decrypted = self._decrypt_password(
                settings["proxy_password_encrypted"])
            self.proxy_password_entry.value = decrypted
        elif "proxy_password" in settings:
            # 旧形式（平文保存）との互換
            self.proxy_password_entry.value = settings["proxy_password"]

        locale_value = settings.get("locale")
        if isinstance(locale_value, str) and locale_value.strip():
            self.i18n.change_language(locale_value.strip())

    def can_run(self) -> bool:
        """実行可能な入力状態かを返す."""
        package_file_path = self.package_file_path.strip()
        output_dir = self.out_entry.value.strip()
        repo_file_path = self.repo_file_path.strip()
        return bool(package_file_path and output_dir
                    and os.path.isfile(package_file_path)
                    and os.path.isfile(repo_file_path))

    def update_run_button_state(self) -> None:
        """入力状態に応じて実行ボタンの活性/非活性を切り替える."""
        self.run_button.config(
            state=tk.NORMAL if self.can_run() else tk.DISABLED, )
        package_file_ready = bool(self.package_file_path
                                  and os.path.isfile(self.package_file_path))
        self.package_edit_btn.config(
            state=tk.NORMAL if package_file_ready else tk.DISABLED)

    def select_repo_file(self) -> None:
        """REPOS.jsonファイルを選択するダイアログを表示し、選択されたファイルパスを保存する. """
        initial_dir = str(get_documents_dir())
        initial_file = ""
        if self.repo_file_path:
            if os.path.isfile(self.repo_file_path):
                initial_dir = os.path.dirname(self.repo_file_path)
                initial_file = os.path.basename(self.repo_file_path)
            elif os.path.isdir(self.repo_file_path):
                initial_dir = self.repo_file_path

        path = filedialog.askopenfilename(title=self.i18n.t("select_repo_file"),
                                          filetypes=[("JSONファイル", "*.json"),
                                                     ("すべてのファイル", "*.*")],
                                          initialdir=initial_dir,
                                          initialfile=initial_file)
        if path:
            self.repo_file_path = path
            self.repo_file_label.config(text=self.i18n.t(
                "repo_file_label", name=os.path.basename(path)))
            if self.repo_editor_window and self.repo_editor_window.winfo_exists(
            ):
                self.repo_editor_window.set_repo_file_path(path)
            self.update_run_button_state()

    def select_package_file(self) -> None:
        """パッケージリストJSONファイルを選択する."""
        initial_dir = self._last_package_file_dir or str(get_documents_dir())
        initial_file = ""
        if self.package_file_path:
            if os.path.isfile(self.package_file_path):
                initial_dir = os.path.dirname(self.package_file_path)
                initial_file = os.path.basename(self.package_file_path)
            elif os.path.isdir(self.package_file_path):
                initial_dir = self.package_file_path

        path = filedialog.askopenfilename(
            title=self.i18n.t("select_package_file"),
            filetypes=[("JSONファイル", "*.json"), ("すべてのファイル", "*.*")],
            initialdir=initial_dir,
            initialfile=initial_file,
        )
        if path:
            self.package_file_path = path
            self._last_package_file_dir = os.path.dirname(path)
            self.package_file_label.config(text=self.i18n.t(
                "package_file_label", name=os.path.basename(path)))
            if (self.package_editor_window
                    and self.package_editor_window.winfo_exists()):
                self.package_editor_window.set_package_file_path(path)
            self.update_run_button_state()

    def create_new_package_file(self) -> None:
        """新しいパッケージリストJSONファイルを作成する."""
        initial_dir = self._last_package_file_dir or str(get_documents_dir())
        path = filedialog.asksaveasfilename(
            title=self.i18n.t("create_package_file"),
            defaultextension=".json",
            filetypes=[("JSONファイル", "*.json"), ("すべてのファイル", "*.*")],
            initialdir=initial_dir,
            initialfile="PACKAGES.json",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=4)
            f.write("\n")

        self.package_file_path = path
        self._last_package_file_dir = os.path.dirname(path)
        self.package_file_label.config(
            text=self.i18n.t("package_file_label", name=os.path.basename(path)))

        if (self.package_editor_window
                and self.package_editor_window.winfo_exists()):
            self.package_editor_window.set_package_file_path(path)
        else:
            self.open_package_editor()
        self.update_run_button_state()

    def open_package_editor(self) -> None:
        """パッケージリスト編集ウィンドウを開く."""
        if (self.package_editor_window
                and self.package_editor_window.winfo_exists()):
            self.package_editor_window.lift()
            self.package_editor_window.focus_force()
            return

        if not self.package_file_path:
            messagebox.showwarning(self.i18n.t("warning"),
                                   self.i18n.t("select_package_file_first"))
            return

        self.package_editor_window = PackageJsonEditorWindow(
            self,
            self.package_file_path,
        )

    def load_service_packages_from_file(self,
                                        path: str) -> list[PackageRequest]:
        """service_type/package_nameのJSONリストを読み込み、返す."""
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)

        if not isinstance(payload, list):
            raise ValueError("JSONのルートは配列である必要があります")

        package_requests: list[PackageRequest] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"{index}件目がオブジェクトではありません")

            service_type = item.get("service_type")
            package_name = item.get("package_name")

            if not isinstance(service_type, str) or not service_type.strip():
                raise ValueError(f"{index}件目のservice_typeが不正です")
            if not isinstance(package_name, str) or not package_name.strip():
                raise ValueError(f"{index}件目のpackage_nameが不正です")

            normalized_service_type = service_type.strip().upper()
            if normalized_service_type not in ("RPM", "DEB"):
                raise ValueError(f"{index}件目のservice_typeはRPMまたはDEBを指定してください")

            package_requests.append(
                PackageRequest(
                    service_type=ServiceType[normalized_service_type],
                    package_name=package_name.strip(),
                ))

        if not package_requests:
            raise ValueError("パッケージが1件もありません")

        return package_requests

    def create_new_repo_file(self) -> None:
        """新しいREPOS.jsonファイルを作成するダイアログを表示し、作成されたファイルパスを保存する. """
        initial_dir = self._last_repo_new_dir or str(get_documents_dir())
        path = filedialog.asksaveasfilename(
            title=self.i18n.t("create_repo_file"),
            defaultextension=".json",
            filetypes=[("JSONファイル", "*.json"), ("すべてのファイル", "*.*")],
            initialdir=initial_dir,
            initialfile="REPOS.json",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=4)
            f.write("\n")

        self.repo_file_path = path
        self._last_repo_new_dir = os.path.dirname(path)
        self.repo_file_label.config(
            text=self.i18n.t("repo_file_label", name=os.path.basename(path)))
        if self.repo_editor_window and self.repo_editor_window.winfo_exists():
            self.repo_editor_window.set_repo_file_path(path)
        else:
            self.open_repo_editor()
        self.update_run_button_state()

    def open_repo_editor(self) -> None:
        """REPOS.json編集ウィンドウを開く. すでに開いている場合はそのウィンドウを前面に表示する. """
        if self.repo_editor_window and self.repo_editor_window.winfo_exists():
            self.repo_editor_window.lift()
            self.repo_editor_window.focus_force()
            return

        self.repo_editor_window = RepoJsonEditorWindow(
            self,
            self.repo_file_path,
        )

    def select_output_dir(self) -> None:
        """ダウンロード先フォルダを選択するダイアログを表示し、選択されたフォルダパスを保存する. """
        initial_dir = self._last_output_dir or str(get_documents_dir())
        path = filedialog.askdirectory(title=self.i18n.t("select_download_dir"),
                                       initialdir=initial_dir)
        if path:
            self.out_entry.value = path
            self._last_output_dir = path
            self.out_label.config(text=f"{self.i18n.t('output_dir')} {path}")
            self.update_run_button_state()

    def on_run(self) -> None:
        """ダウンロード処理を実行する. 入力値の検証とREPOS.jsonの読み込みを行い、ダウンロード処理を別スレッドで実行する. """
        if not self.can_run():
            return

        use_proxy = self.use_proxy_checkbox.value
        proxy_url = self.proxy_url_entry.value.strip()
        proxy_username = self.proxy_username_entry.value.strip()
        proxy_password = self.proxy_password_entry.value.strip()
        if use_proxy and not proxy_url:
            messagebox.showwarning(self.i18n.t("warning"),
                                   self.i18n.t("proxy_url_required"))
            return

        package_file_path = self.package_file_path.strip()
        try:
            package_requests = self.load_service_packages_from_file(
                package_file_path)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            messagebox.showerror(
                self.i18n.t("error"),
                self.i18n.t("package_list_load_failed", error=e))
            return

        # 入力値取得
        output_dir = self.out_entry.value
        arch = self.arch_combobox.value.strip() or None
        dry_run = False
        rpm_probe = False

        # REPOS.jsonファイル選択
        repos_path = self.repo_file_path

        # REPOS.jsonからリスト取得
        with open(repos_path, encoding="utf-8") as f:
            repos_json = json.load(f)
        repos = [
            ServiceRepo(service_type=ServiceType[item["service_type"]],
                        repo_url=item["repo_url"],
                        enable=item.get("enable", True)) for item in repos_json
        ]

        # downloader.runをスレッドで実行
        self.open_log_output_window()
        self._stream_capture.start()

        def task() -> None:
            """on_run 内で定義されたローカル関数.

            self を引数に取らず、on_run のローカル変数をクロージャで参照して
            ダウンロード処理を別スレッドで実行する.
            """
            task_error = None
            try:
                self.proxy_manager.set_proxy(
                    use_proxy=use_proxy,
                    url=proxy_url,
                    username=proxy_username,
                    password=proxy_password,
                )
                run(
                    package_names=[],
                    output_dir=output_dir,
                    repos=repos,
                    arch=arch,
                    dry_run=dry_run,
                    rpm_probe=rpm_probe,
                    package_requests=package_requests,
                )
            except Exception as e:  # pylint: disable=broad-except
                task_error = e
                traceback.print_exc()
            finally:
                self.proxy_manager.restore_proxy()
                self.after(0, self._stream_capture.stop)
                self.after(0, self._show_run_result_dialog, task_error)

        threading.Thread(target=task, daemon=True).start()

    def add_run_button(self) -> None:
        """実行ボタンを追加する. すでに存在する場合は何もしない. """
        btn = tk.Button(self, text=self.i18n.t("run"), command=self.on_run)
        btn.pack(pady=20)


if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
