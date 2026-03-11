"""Tkinter application orchestration for ewptools."""

from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from ewptools.constants import DEFAULT_EXTENSION_TEXT
from ewptools.project import EwpProject

from .feedback import AppFeedback
from .input_utils import (
    default_extension_text,
    merge_input_paths,
    parse_extensions,
    parse_input_paths,
    split_existing_paths,
)
from .project_tree import ProjectTreeController


@dataclass(frozen=True)
class AddPathsRequest:
    directories: list[str]
    files: list[str]
    group_name: str | None
    parent_group_path: str | None
    extensions: set[str]
    recursive: bool
    sync_ewt: bool
    sync_include_paths: bool


class EwpToolsApp:
    """Tkinter GUI for managing `.ewp` project groups and files."""

    def __init__(self, root: tk.Tk, ewp_path: str | None = None):
        self.root = root
        self.root.title("ewptools - IAR 项目管理")
        self.root.geometry("980x640")
        self.root.minsize(600, 450)

        self.proj: EwpProject | None = None
        self.tree_controller: ProjectTreeController | None = None
        self.feedback: AppFeedback | None = None

        self._build_ui()

        if ewp_path and os.path.isfile(ewp_path):
            self.ewp_var.set(ewp_path)
            self._load_project()

    def _build_ui(self) -> None:
        self._build_project_selector()
        content = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._build_tree_panel(content)
        self._build_action_panel(content)
        self._build_status_bar()
        self._build_log_panel()

    def _build_project_selector(self) -> None:
        top_frame = ttk.LabelFrame(self.root, text="项目文件", padding=8)
        top_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        self.ewp_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.ewp_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(top_frame, text="浏览...", command=self._browse_ewp).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top_frame, text="加载", command=self._load_project).pack(side=tk.LEFT)

    def _build_tree_panel(self, content: ttk.PanedWindow) -> None:
        tree_frame = ttk.LabelFrame(content, text="项目结构", padding=8)
        content.add(tree_frame, weight=3)

        tree_toolbar = ttk.Frame(tree_frame)
        tree_toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(tree_toolbar, text="刷新", command=lambda: self._refresh_tree(preserve_state=True)).pack(side=tk.LEFT)
        self.tree_toggle_text = tk.StringVar(value="展开全部")
        ttk.Button(tree_toolbar, textvariable=self.tree_toggle_text, command=self._toggle_tree_expand_collapse).pack(
            side=tk.LEFT,
            padx=(6, 0),
        )

        tree_body = ttk.Frame(tree_frame)
        tree_body.pack(fill=tk.BOTH, expand=True)
        tree_body.columnconfigure(0, weight=1)
        tree_body.rowconfigure(0, weight=1)

        tree_scroll = ttk.Scrollbar(tree_body, orient=tk.VERTICAL)
        tree_xscroll = ttk.Scrollbar(tree_body, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(
            tree_body,
            yscrollcommand=tree_scroll.set,
            xscrollcommand=tree_xscroll.set,
            selectmode="browse",
        )
        tree_scroll.config(command=self.tree.yview)
        tree_xscroll.config(command=self.tree.xview)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")
        tree_xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.heading("#0", text="分组 / 文件", anchor=tk.W)
        self.tree.column("#0", width=500, minwidth=220, stretch=False)
        self.tree_controller = ProjectTreeController(self.tree, self.tree_toggle_text)

    def _build_action_panel(self, content: ttk.PanedWindow) -> None:
        action_frame = ttk.LabelFrame(content, text="操作面板", padding=10)
        content.add(action_frame, weight=2)
        action_frame.columnconfigure(1, weight=1)

        ttk.Label(action_frame, text="路径:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.dir_var = tk.StringVar()
        ttk.Entry(action_frame, textvariable=self.dir_var).grid(row=0, column=1, sticky="ew", pady=(0, 6))
        select_frame = ttk.Frame(action_frame)
        select_frame.grid(row=0, column=2, padx=(6, 0), pady=(0, 6), sticky="ew")
        ttk.Button(select_frame, text="选文件夹", command=self._pick_dirs).pack(side=tk.LEFT)
        ttk.Button(select_frame, text="选文件", command=self._pick_files).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(action_frame, text="Group 名:").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.group_name_var = tk.StringVar()
        ttk.Entry(action_frame, textvariable=self.group_name_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(0, 6))

        ttk.Label(action_frame, text="扩展名:").grid(row=2, column=0, sticky="w", pady=(0, 6))
        self.ext_var = tk.StringVar(value=DEFAULT_EXTENSION_TEXT)
        ttk.Entry(action_frame, textvariable=self.ext_var).grid(row=2, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(action_frame, text="推荐", command=self._reset_default_extensions).grid(row=2, column=2, padx=(6, 0), pady=(0, 6))

        option_frame = ttk.LabelFrame(action_frame, text="选项", padding=8)
        option_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        self.recursive_var = tk.BooleanVar(value=True)
        self.include_headers_var = tk.BooleanVar(value=True)
        self.sync_include_path_var = tk.BooleanVar(value=True)
        self.sync_ewt_var = tk.BooleanVar(value=True)
        self.add_to_selected_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(option_frame, text="递归子目录", variable=self.recursive_var).pack(anchor="w")
        ttk.Checkbutton(option_frame, text="包含头文件", variable=self.include_headers_var).pack(anchor="w")
        ttk.Checkbutton(option_frame, text="同步 Include Path", variable=self.sync_include_path_var).pack(anchor="w")
        ttk.Checkbutton(option_frame, text="同步 .ewt（工程结构）", variable=self.sync_ewt_var).pack(anchor="w")
        ttk.Checkbutton(option_frame, text="添加到选中的 Group 下", variable=self.add_to_selected_var).pack(anchor="w")

        ttk.Button(action_frame, text="添加路径（文件/目录）", command=self._add_paths).grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 6),
        )
        ttk.Button(action_frame, text="仅同步 Include Path", command=self._sync_include_path_only).grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 6),
        )
        ttk.Button(action_frame, text="删除选中项", command=self._remove_selected).grid(row=6, column=0, columnspan=3, sticky="ew")

    def _build_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="未加载项目")
        ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X, padx=10, pady=(0, 8))

    def _build_log_panel(self) -> None:
        log_frame = ttk.LabelFrame(self.root, text="日志", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, pady=(0, 4))
        self.log_text = ScrolledText(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.feedback = AppFeedback(self.status_var, self.log_text)
        ttk.Button(log_toolbar, text="清空日志", command=self.feedback.clear_log).pack(side=tk.RIGHT)

    def _ok(self, text: str) -> None:
        self.feedback.ok(text)

    def _warn(self, text: str) -> None:
        self.feedback.warn(text)

    def _err(self, text: str, exc: Exception | None = None) -> None:
        self.feedback.error(text, exc)

    def _ensure_project(self) -> bool:
        if self.proj:
            return True
        messagebox.showwarning("提示", "请先加载 .ewp 项目文件")
        return False

    def _refresh_tree(self, preserve_state: bool = False) -> None:
        if not self.proj:
            return
        self.tree_controller.refresh(self.proj.root, preserve_state=preserve_state)
        self._ok(f"树已刷新: {os.path.basename(self.proj.ewp_path)}")

    def _save_and_refresh(self, sync_ewt: bool) -> list[str]:
        saved_paths = self.proj.save(save_ewt=sync_ewt)
        self._refresh_tree(preserve_state=True)
        for path in saved_paths:
            self.feedback.log(f"[SAVE] {path}")
        return saved_paths

    def _selected_parent_group(self) -> str | None:
        if not self.add_to_selected_var.get():
            return None
        parent_path = self.tree_controller.selected_group_path()
        if parent_path:
            return parent_path
        messagebox.showwarning("提示", "请在树中选择一个父 Group")
        return None

    def _browse_ewp(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 .ewp 文件",
            filetypes=[("IAR 项目文件", "*.ewp"), ("所有文件", "*.*")],
        )
        if path:
            self.ewp_var.set(path)
            self._load_project()

    def _pick_dirs(self) -> None:
        initial = self.proj.proj_dir if self.proj else ""
        path = filedialog.askdirectory(title="选择文件夹", initialdir=initial)
        if not path:
            return
        self._set_path_list([path], append=True)
        self._ok("已选择文件夹: 1")

    def _pick_files(self) -> None:
        initial = self.proj.proj_dir if self.proj else ""
        files = filedialog.askopenfilenames(
            title="选择文件（可多选）",
            initialdir=initial,
            filetypes=[("所有文件", "*.*")],
        )
        if not files:
            return
        self._set_path_list(list(files), append=True)
        self._ok(f"已选择文件: {len(files)}")

    def _set_path_list(self, paths: list[str], append: bool) -> None:
        self.dir_var.set(merge_input_paths(self.dir_var.get(), paths, append=append))

    def _load_project(self) -> None:
        path = self.ewp_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("错误", f"文件不存在: {path}")
            return
        try:
            self.proj = EwpProject(path)
            self.root.title(f"ewptools - {os.path.basename(path)}")
            self._refresh_tree()
            if self.proj.ewt_path:
                self._ok(f"已加载项目: {path} (检测到并同步 .ewt)")
            else:
                self.sync_ewt_var.set(False)
                self._warn(f"已加载项目: {path} (未检测到同名 .ewt)")
        except Exception as exc:
            self._err("解析失败", exc)

    def _toggle_tree_expand_collapse(self) -> None:
        expand = self.tree_controller.toggle_expand_collapse()
        self._ok("已展开全部节点" if expand else "已折叠全部节点")

    def _reset_default_extensions(self) -> None:
        self.ext_var.set(default_extension_text())
        self.include_headers_var.set(True)
        self._ok("已恢复推荐扩展名，并启用包含头文件")

    def _sync_ewt_enabled(self) -> bool:
        return bool(self.sync_ewt_var.get() and self.proj and self.proj.ewt_path)

    def _build_add_request(self) -> AddPathsRequest | None:
        paths = parse_input_paths(self.dir_var.get())
        directories, files = split_existing_paths(paths)
        if not directories and not files:
            messagebox.showwarning("提示", "请至少选择一个有效路径（文件或目录，可用分号分隔）")
            return None

        parent_group_path = self._selected_parent_group()
        if self.add_to_selected_var.get() and parent_group_path is None:
            return None

        return AddPathsRequest(
            directories=directories,
            files=files,
            group_name=self.group_name_var.get().strip() or None,
            parent_group_path=parent_group_path,
            extensions=parse_extensions(self.ext_var.get(), self.include_headers_var.get()),
            recursive=self.recursive_var.get(),
            sync_ewt=self._sync_ewt_enabled(),
            sync_include_paths=self.sync_include_path_var.get(),
        )

    def _add_paths(self) -> None:
        if not self._ensure_project():
            return

        request = self._build_add_request()
        if request is None:
            return

        try:
            added_dir_files = 0
            added_files = 0
            include_added = 0

            for dir_path in request.directories:
                current_group_name = request.group_name if (len(request.directories) == 1 and request.group_name) else os.path.basename(dir_path)
                added_dir_files += self.proj.add_directory(
                    dir_path=dir_path,
                    group_name=current_group_name,
                    parent_group_path=request.parent_group_path,
                    extensions=request.extensions,
                    recursive=request.recursive,
                    sync_ewt=request.sync_ewt,
                )

                if request.sync_include_paths:
                    include_added += self.proj.add_include_paths_from_directory(dir_path, recursive=request.recursive)

            if request.files:
                added_files = self.proj.add_files(
                    file_paths=request.files,
                    parent_group_path=request.parent_group_path,
                    group_name=request.group_name,
                    sync_ewt=request.sync_ewt,
                )
                if request.sync_include_paths:
                    include_added += self.proj.add_include_paths_from_files(request.files)

            saved_paths = self._save_and_refresh(request.sync_ewt)
            self._ok(
                f"路径添加完成: 目录 {len(request.directories)}，目录新增文件 {added_dir_files}，"
                f"文件条目新增 {added_files}，Include Path {include_added}，保存 {len(saved_paths)} 个文件"
            )
            self.dir_var.set("")
            self.group_name_var.set("")
        except Exception as exc:
            self._err("添加路径失败", exc)

    def _remove_selected(self) -> None:
        if not self._ensure_project():
            return

        selection = self.tree_controller.selected_item()
        if selection.item_type not in {"group", "file"} or not selection.path:
            messagebox.showwarning("提示", "请在树中选择要删除的 Group 或 File")
            return

        prompt = (
            f"确定要删除 Group '{selection.path}' 吗？\n\n注意：仅删除工程结构，不删除磁盘文件。"
            if selection.item_type == "group"
            else f"确定要删除 File 条目 '{selection.path}' 吗？\n\n注意：仅删除工程结构，不删除磁盘文件。"
        )
        if not messagebox.askyesno("确认删除", prompt):
            return

        try:
            sync_ewt = self._sync_ewt_enabled()
            if selection.item_type == "group":
                removed_files = self.proj.remove_group(selection.path, sync_ewt=sync_ewt)
                action_text = f"已删除 Group: {selection.path}"
            else:
                removed_files = self.proj.remove_file(selection.path, sync_ewt=sync_ewt)
                if not removed_files:
                    messagebox.showerror("错误", f"未找到 File 条目: {selection.path}")
                    return
                action_text = f"已删除 File: {selection.path}"

            include_removed = self.proj.remove_include_paths_for_files(removed_files) if self.sync_include_path_var.get() and removed_files else 0
            saved_paths = self._save_and_refresh(sync_ewt)
            self._ok(f"{action_text}，清理 Include Path {include_removed} 条，保存 {len(saved_paths)} 个文件")
        except Exception as exc:
            self._err("删除失败", exc)

    def _sync_include_path_only(self) -> None:
        if not self._ensure_project():
            return

        directories, _ = split_existing_paths(parse_input_paths(self.dir_var.get()))
        if not directories:
            messagebox.showwarning("提示", "请至少选择一个有效文件夹")
            return

        try:
            sync_ewt = self._sync_ewt_enabled()
            include_added = 0
            for dir_path in directories:
                include_added += self.proj.add_include_paths_from_directory(dir_path, recursive=self.recursive_var.get())
            saved_paths = self._save_and_refresh(sync_ewt)
            self._ok(f"Include Path 同步完成: 新增 {include_added}，保存 {len(saved_paths)} 个文件")
        except Exception as exc:
            self._err("Include Path 同步失败", exc)


