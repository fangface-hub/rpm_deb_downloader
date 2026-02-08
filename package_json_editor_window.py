#!/usr/bin/env python3
"""package.json編集ウィンドウの実装."""
import json
import tkinter as tk
from tkinter import messagebox

from i18n import I18n
from treeviewex import TreeviewEx


class PackageJsonEditorWindow(tk.Toplevel):
    """package.json編集ウィンドウクラス."""

    def __init__(self, master, package_file_path: str):
        super().__init__(master)
        self.i18n = getattr(master, "i18n", I18n())
        self.title(self.i18n.t("package_editor_title"))
        self.geometry("700x500")
        self.package_file_path = package_file_path

        self.path_label = tk.Label(self, anchor="w")
        self.path_label.pack(fill="x", padx=10, pady=(10, 0))

        self.tree = TreeviewEx(
            self,
            columns=("service_type", "package_name"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("service_type", text="service_type")
        self.tree.heading("package_name", text="package_name")
        self.tree.column("service_type", width=140)
        self.tree.column("package_name", width=520)
        self.tree.set_combobox_column("#1", ["RPM", "DEB"])
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

        button_frame = tk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.add_row_button = tk.Button(button_frame,
                                        text=self.i18n.t("add_row"),
                                        command=self.add_row)
        self.add_row_button.pack(side="left")
        self.delete_row_button = tk.Button(
            button_frame,
            text=self.i18n.t("delete_selected_row"),
            command=self.delete_selected_row)
        self.delete_row_button.pack(side="left", padx=5)
        self.reload_button = tk.Button(button_frame,
                                       text=self.i18n.t("reload"),
                                       command=self.reload_from_file)
        self.reload_button.pack(side="left", padx=5)
        self.save_button = tk.Button(button_frame,
                                     text=self.i18n.t("save"),
                                     command=self.save_to_file)
        self.save_button.pack(side="left", padx=5)
        self.close_button = tk.Button(button_frame,
                                      text=self.i18n.t("close"),
                                      command=self.destroy)
        self.close_button.pack(side="right")

        self.reload_from_file()

    def set_package_file_path(self, package_file_path: str) -> None:
        """編集対象のpackage.jsonファイルパスを設定し再読み込みする."""
        self.package_file_path = package_file_path
        self.reload_from_file()

    def reload_from_file(self) -> None:
        """現在のpackage_file_pathで指定されたファイルを読み込み表示する."""
        self.path_label.config(
            text=self.i18n.t("editing_target", path=self.package_file_path))
        try:
            with open(self.package_file_path, encoding="utf-8") as f:
                rows = json.load(f)
        except OSError as e:
            messagebox.showerror(self.i18n.t("load_error"),
                                 self.i18n.t("file_load_failed", error=e))
            return
        except json.JSONDecodeError as e:
            messagebox.showerror(self.i18n.t("json_error"),
                                 self.i18n.t("invalid_json", error=e))
            return

        if not isinstance(rows, list):
            messagebox.showerror(self.i18n.t("json_error"),
                                 self.i18n.t("json_root_must_be_array"))
            return

        self.tree.delete(*self.tree.get_children())
        for row in rows:
            if not isinstance(row, dict):
                continue
            service_type = str(row.get("service_type", "")).upper()
            package_name = str(row.get("package_name", ""))
            self.tree.insert("", "end", values=(service_type, package_name))

    def add_row(self) -> None:
        """新しい行を追加する."""
        row_id = self.tree.insert("", "end", values=("RPM", ""))
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)

    def delete_selected_row(self) -> None:
        """選択されている行を削除する."""
        selected = self.tree.selection()
        if not selected:
            return
        for row_id in selected:
            self.tree.delete(row_id)

    def save_to_file(self) -> None:
        """現在のTreeviewの内容をファイルに保存する."""
        parsed = []
        for row_number, row_id in enumerate(self.tree.get_children(), start=1):
            service_type, package_name = self.tree.item(row_id, "values")
            service_type = service_type.strip().upper()
            package_name = package_name.strip()

            if service_type not in ("RPM", "DEB"):
                messagebox.showerror(
                    self.i18n.t("input_error"),
                    self.i18n.t("service_type_invalid_row", row=row_number),
                )
                return

            if not package_name:
                messagebox.showerror(
                    self.i18n.t("input_error"),
                    self.i18n.t("package_name_required_row", row=row_number),
                )
                return

            parsed.append({
                "service_type": service_type,
                "package_name": package_name,
            })

        try:
            with open(self.package_file_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=4)
                f.write("\n")
        except OSError as e:
            messagebox.showerror(self.i18n.t("save_error"),
                                 self.i18n.t("file_save_failed", error=e))
            return

        messagebox.showinfo(self.i18n.t("save_completed"),
                            self.i18n.t("package_saved"))
