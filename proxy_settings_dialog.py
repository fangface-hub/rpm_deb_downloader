"""プロキシ設定ダイアログ"""

import tkinter as tk
from tkinter import ttk

from i18n import I18n
from tkinterex import CustomCheckbutton, CustomEntry


class ProxySettingsDialog(tk.Toplevel):
    """プロキシ設定ダイアログ"""

    def __init__(self, parent, main_gui):
        """
        初期化

        Args:
            parent: 親ウィンドウ
            main_gui: メインGUIインスタンス
        """
        super().__init__(parent)
        self.main_gui = main_gui
        self.i18n = getattr(main_gui, "i18n", I18n())

        # ウィンドウ設定
        self.title(self.i18n.t("proxy_dialog_title"))
        self.geometry("450x250")
        self.resizable(False, True)

        # ウィンドウが閉じられる時の処理
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.create_widgets()

    def create_widgets(self):
        """ウィジェットを作成"""
        main_frame = ttk.Frame(self, padding="20")
        main_frame.grid(row=0, column=0, sticky="wens")

        # プロキシを使用するかのチェックボックス
        self.use_proxy_checkbox = CustomCheckbutton(
            main_frame,
            text=self.i18n.t("use_proxy"),
            command=self.toggle_proxy_fields,
        )
        self.use_proxy_checkbox.value = self.main_gui.use_proxy_checkbox.value
        self.use_proxy_checkbox.grid(row=0,
                                     column=0,
                                     columnspan=2,
                                     padx=5,
                                     pady=5,
                                     sticky=tk.W)

        # プロキシURL
        ttk.Label(main_frame, text=self.i18n.t("proxy_url")).grid(
            row=1,
            column=0,
            sticky=tk.W,
            padx=5,
            pady=5,
        )
        self.proxy_url_entry = CustomEntry(main_frame, width=35)
        self.proxy_url_entry.value = self.main_gui.proxy_url_entry.value
        self.proxy_url_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # ユーザー名
        ttk.Label(main_frame, text=self.i18n.t("username")).grid(
            row=2,
            column=0,
            sticky=tk.W,
            padx=5,
            pady=5,
        )
        self.proxy_username_entry = CustomEntry(main_frame, width=35)
        username_value = self.main_gui.proxy_username_entry.value
        self.proxy_username_entry.value = username_value
        self.proxy_username_entry.grid(row=2,
                                       column=1,
                                       padx=5,
                                       pady=5,
                                       sticky="ew")

        # パスワード
        ttk.Label(main_frame, text=self.i18n.t("password")).grid(
            row=3,
            column=0,
            sticky=tk.W,
            padx=5,
            pady=5,
        )
        self.proxy_password_entry = CustomEntry(main_frame, width=35, show="*")
        password_value = self.main_gui.proxy_password_entry.value
        self.proxy_password_entry.value = password_value
        self.proxy_password_entry.grid(row=3,
                                       column=1,
                                       padx=5,
                                       pady=5,
                                       sticky="ew")

        # ボタンフレーム
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=20)

        ttk.Button(button_frame, text=self.i18n.t("ok"),
                   command=self.on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame,
                   text=self.i18n.t("cancel"),
                   command=self.on_close).pack(side=tk.LEFT, padx=5)

        # 初期状態ではプロキシ入力欄を無効化
        self.toggle_proxy_fields()

        main_frame.columnconfigure(1, weight=1)

    def toggle_proxy_fields(self):
        """プロキシフィールドの有効/無効をトグル"""
        state = tk.NORMAL if self.use_proxy_checkbox.value else tk.DISABLED
        self.proxy_url_entry.config(state=state)
        self.proxy_username_entry.config(state=state)
        self.proxy_password_entry.config(state=state)

    def on_ok(self):
        """OK ボタン押下 - 設定をメインGUIに反映"""
        self.main_gui.use_proxy_checkbox.value = self.use_proxy_checkbox.value
        self.main_gui.proxy_url_entry.value = self.proxy_url_entry.value.strip()
        self.main_gui.proxy_username_entry.value = (
            self.proxy_username_entry.value.strip())
        self.main_gui.proxy_password_entry.value = (
            self.proxy_password_entry.value.strip())
        self.main_gui.toggle_proxy_fields()
        self.on_close()

    def on_close(self):
        """ウィンドウを閉じる"""
        self.destroy()
