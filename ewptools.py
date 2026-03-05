"""ewptools GUI - IAR Embedded Workbench (.ewp) 项目文件管理工具。"""

import xml.etree.ElementTree as ET
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox


# 常见的源文件和工程相关扩展名
DEFAULT_SOURCE_EXTENSIONS = {
    '.c', '.cpp', '.cxx', '.cc',
    '.s', '.asm',
    '.icf',  # linker script
    '.inc',
}

# 头文件扩展名（编译和索引通常需要）
HEADER_FILE_EXTENSIONS = {
    '.h', '.hpp', '.hh', '.hxx', '.inl', '.tpp'
}


class EwpProject:
    """IAR .ewp 项目文件操作类"""

    def __init__(self, ewp_path: str):
        self.ewp_path = os.path.abspath(ewp_path)
        self.proj_dir = os.path.dirname(self.ewp_path)
        self.tree = ET.parse(self.ewp_path)
        self.root = self.tree.getroot()

    def save(self, output_path: str = None):
        """保存 .ewp 文件"""
        path = output_path or self.ewp_path
        ET.indent(self.tree, space="    ")
        self.tree.write(path, encoding="UTF-8", xml_declaration=True)
        # ET.write 写的是 <?xml version='1.0' encoding='UTF-8'?>（单引号）
        # IAR 使用双引号，这里做一个替换以保持兼容
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace("<?xml version='1.0' encoding='UTF-8'?>",
                                  '<?xml version="1.0" encoding="UTF-8"?>')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] 已保存: {path}")

    def _to_proj_dir_path(self, abs_path: str) -> str:
        """将绝对路径转换为 $PROJ_DIR$ 相对路径"""
        try:
            rel = os.path.relpath(abs_path, self.proj_dir)
            return f"$PROJ_DIR$\\{rel}"
        except ValueError:
            # 不同盘符时无法生成相对路径，使用绝对路径
            return abs_path

    def _find_group(self, parent: ET.Element, group_name: str) -> ET.Element:
        """在 parent 下查找名为 group_name 的 group"""
        for group in parent.findall('group'):
            name_elem = group.find('name')
            if name_elem is not None and name_elem.text == group_name:
                return group
        return None

    def _find_or_create_group(self, parent: ET.Element, group_name: str) -> ET.Element:
        """在 parent 下找到或创建一个 group"""
        existing = self._find_group(parent, group_name)
        if existing is not None:
            return existing
        group = ET.SubElement(parent, 'group')
        name = ET.SubElement(group, 'name')
        name.text = group_name
        return group

    def _get_existing_files(self, group: ET.Element) -> set:
        """获取 group 中已有的文件路径集合"""
        files = set()
        for file_elem in group.findall('file'):
            name_elem = file_elem.find('name')
            if name_elem is not None and name_elem.text:
                files.add(name_elem.text)
        return files

    def _add_file_to_group(self, group: ET.Element, proj_dir_path: str):
        """向 group 添加一个文件（如果不存在）"""
        existing = self._get_existing_files(group)
        if proj_dir_path in existing:
            return False
        file_elem = ET.SubElement(group, 'file')
        name_elem = ET.SubElement(file_elem, 'name')
        name_elem.text = proj_dir_path
        return True

    def _find_or_create_compiler_include_option(self, config: ET.Element) -> ET.Element:
        """在配置中找到(或创建)编译器 Include Path 选项。"""
        icc_settings = None
        for settings in config.findall('settings'):
            name_elem = settings.find('name')
            if name_elem is not None and name_elem.text and name_elem.text.startswith('ICC'):
                icc_settings = settings
                data = settings.find('data')
                if data is None:
                    data = ET.SubElement(settings, 'data')

                # 常见 IAR 选项名: CCIncludePath2
                for option in data.findall('option'):
                    opt_name = option.find('name')
                    if opt_name is not None and opt_name.text in ('CCIncludePath2', 'CCIncludePath'):
                        return option

        if icc_settings is None:
            return None

        data = icc_settings.find('data')
        if data is None:
            data = ET.SubElement(icc_settings, 'data')

        option = ET.SubElement(data, 'option')
        option_name = ET.SubElement(option, 'name')
        option_name.text = 'CCIncludePath2'
        return option

    def _normalize_proj_path(self, path_value: str) -> str:
        """规范化路径字符串，便于做去重比较。"""
        if not path_value:
            return ''
        return path_value.replace('/', '\\').rstrip('\\')

    def _collect_include_dirs(self, base_dir: str, recursive: bool = True) -> list:
        """收集包含头文件的目录，并转换为 $PROJ_DIR$ 路径。"""
        base_dir = os.path.abspath(base_dir)
        include_dirs = set()

        for root, dirs, files in os.walk(base_dir):
            if not recursive:
                dirs[:] = []
            else:
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'node_modules')]

            has_header = False
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext in HEADER_FILE_EXTENSIONS:
                    has_header = True
                    break

            if has_header:
                include_dirs.add(self._to_proj_dir_path(root))

        # 稳定排序，避免每次写入顺序变化
        return sorted(include_dirs)

    def add_include_paths_from_directory(self, base_dir: str, recursive: bool = True):
        """将目录中发现的头文件目录追加到各配置的编译器 Include Path。"""
        include_dirs = self._collect_include_dirs(base_dir, recursive=recursive)
        if not include_dirs:
            return 0

        added_count = 0
        for config in self.root.findall('configuration'):
            option = self._find_or_create_compiler_include_option(config)
            if option is None:
                continue

            existing = set()
            for state in option.findall('state'):
                existing.add(self._normalize_proj_path(state.text or ''))

            for inc_dir in include_dirs:
                norm = self._normalize_proj_path(inc_dir)
                if norm not in existing:
                    state = ET.SubElement(option, 'state')
                    state.text = inc_dir
                    existing.add(norm)
                    added_count += 1

        return added_count

    def add_directory(self, dir_path: str, group_name: str = None,
                      parent_group_path: str = None,
                      extensions: set = None, recursive: bool = True):
        """
        添加一个目录到项目中。

        Args:
            dir_path: 要添加的目录的绝对或相对路径
            group_name: group 名称，默认使用目录名
            parent_group_path: 父 group 路径，用 '/' 分隔，如 "Source/Drivers"
            extensions: 要包含的文件扩展名集合
            recursive: 是否递归添加子目录
        """
        dir_path = os.path.abspath(dir_path)
        if not os.path.isdir(dir_path):
            print(f"[错误] 目录不存在: {dir_path}")
            return

        if extensions is None:
            extensions = DEFAULT_SOURCE_EXTENSIONS

        if group_name is None:
            group_name = os.path.basename(dir_path)

        # 定位父节点
        parent = self.root
        if parent_group_path:
            parts = parent_group_path.strip('/').split('/')
            for part in parts:
                parent = self._find_or_create_group(parent, part)

        # 递归添加
        added_count = self._add_dir_recursive(parent, dir_path, group_name,
                                               extensions, recursive)
        print(f"[OK] 已添加 {added_count} 个文件到 group '{group_name}'")
        return added_count

    def _add_dir_recursive(self, parent: ET.Element, dir_path: str,
                           group_name: str, extensions: set,
                           recursive: bool) -> int:
        """递归地将目录结构添加为 group/file 结构"""
        group = self._find_or_create_group(parent, group_name)
        added = 0

        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            print(f"[警告] 无权访问: {dir_path}")
            return 0

        # 先添加文件
        for entry in entries:
            full_path = os.path.join(dir_path, entry)
            if os.path.isfile(full_path):
                ext = os.path.splitext(entry)[1].lower()
                if ext in extensions:
                    proj_path = self._to_proj_dir_path(full_path)
                    if self._add_file_to_group(group, proj_path):
                        added += 1

        # 再递归子目录
        if recursive:
            for entry in entries:
                full_path = os.path.join(dir_path, entry)
                if os.path.isdir(full_path):
                    # 跳过常见的不需要的目录
                    if entry.startswith('.') or entry in ('__pycache__', 'node_modules'):
                        continue
                    added += self._add_dir_recursive(group, full_path, entry,
                                                      extensions, recursive)
        return added

    def remove_group(self, group_path: str):
        """
        删除指定路径的 group。

        Args:
            group_path: group 路径，用 '/' 分隔，如 "Source/Drivers"
        """
        parts = group_path.strip('/').split('/')
        if not parts:
            print("[错误] group 路径不能为空")
            return

        # 找到父节点和目标节点
        parent = self.root
        target = None
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                target = self._find_group(parent, part)
                if target is None:
                    print(f"[错误] 未找到 group: {group_path}")
                    return
                parent.remove(target)
                print(f"[OK] 已删除 group: {group_path}")
                return
            else:
                next_parent = self._find_group(parent, part)
                if next_parent is None:
                    print(f"[错误] 未找到 group: {group_path}")
                    return
                parent = next_parent

class EwpToolsApp:
    """Tkinter GUI for managing .ewp project groups/files."""

    def __init__(self, root: tk.Tk, ewp_path: str = None):
        self.root = root
        self.root.title("ewptools - IAR 项目管理")
        self.root.geometry("980x640")
        self.root.minsize(600, 450)

        self.proj: EwpProject = None
        self._group_paths = {}

        self._build_ui()

        if ewp_path and os.path.isfile(ewp_path):
            self.ewp_var.set(ewp_path)
            self._load_project()

    def _build_ui(self):
        top_frame = ttk.LabelFrame(self.root, text="项目文件", padding=8)
        top_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        self.ewp_var = tk.StringVar()
        ewp_entry = ttk.Entry(top_frame, textvariable=self.ewp_var)
        ewp_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(top_frame, text="浏览...", command=self._browse_ewp).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top_frame, text="加载", command=self._load_project).pack(side=tk.LEFT)

        content = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        tree_frame = ttk.LabelFrame(content, text="项目结构", padding=8)
        content.add(tree_frame, weight=3)

        tree_toolbar = ttk.Frame(tree_frame)
        tree_toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(tree_toolbar, text="刷新", command=self._refresh_tree_preserve_state).pack(side=tk.LEFT)
        self.tree_toggle_text = tk.StringVar(value="展开全部")
        self.tree_toggle_btn = ttk.Button(tree_toolbar, textvariable=self.tree_toggle_text, command=self._toggle_tree_expand_collapse)
        self.tree_toggle_btn.pack(side=tk.LEFT, padx=(6, 0))

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
        # 禁止树列自动拉伸，才能让横向滚动条正确生效。
        self.tree.column("#0", width=500, minwidth=220, stretch=False)

        action_frame = ttk.LabelFrame(content, text="操作面板", padding=10)
        content.add(action_frame, weight=2)
        action_frame.columnconfigure(1, weight=1)

        ttk.Label(action_frame, text="目录:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.dir_var = tk.StringVar()
        ttk.Entry(action_frame, textvariable=self.dir_var).grid(row=0, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(action_frame, text="选择...", command=self._browse_dir).grid(row=0, column=2, padx=(6, 0), pady=(0, 6))

        ttk.Label(action_frame, text="Group 名:").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.group_name_var = tk.StringVar()
        ttk.Entry(action_frame, textvariable=self.group_name_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(0, 6))

        ttk.Label(action_frame, text="扩展名:").grid(row=2, column=0, sticky="w", pady=(0, 6))
        self.ext_var = tk.StringVar(value=".c .cpp .cxx .cc .s .asm .icf .inc")
        ttk.Entry(action_frame, textvariable=self.ext_var).grid(row=2, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(action_frame, text="推荐", command=self._reset_default_extensions).grid(row=2, column=2, padx=(6, 0), pady=(0, 6))

        option_frame = ttk.LabelFrame(action_frame, text="选项", padding=8)
        option_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        self.recursive_var = tk.BooleanVar(value=True)
        self.include_headers_var = tk.BooleanVar(value=True)
        self.sync_include_path_var = tk.BooleanVar(value=True)
        self.add_to_selected_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(option_frame, text="递归子目录", variable=self.recursive_var).pack(anchor="w")
        ttk.Checkbutton(option_frame, text="包含头文件", variable=self.include_headers_var).pack(anchor="w")
        ttk.Checkbutton(option_frame, text="同步 Include Path", variable=self.sync_include_path_var).pack(anchor="w")
        ttk.Checkbutton(option_frame, text="添加到选中的 Group 下", variable=self.add_to_selected_var).pack(anchor="w")

        ttk.Button(action_frame, text="添加文件夹", command=self._add_directory).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        ttk.Button(action_frame, text="仅同步 Include Path", command=self._sync_include_path_only).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        ttk.Button(action_frame, text="删除选中 Group", command=self._remove_selected).grid(row=6, column=0, columnspan=3, sticky="ew")

        self.status_var = tk.StringVar(value="未加载项目")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W)
        status.pack(fill=tk.X, padx=10, pady=(0, 8))

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _reset_default_extensions(self):
        self.ext_var.set(".c .cpp .cxx .cc .s .asm .icf .inc")
        self.include_headers_var.set(True)
        self._set_status("已恢复推荐扩展名，并启用包含头文件")

    def _browse_ewp(self):
        path = filedialog.askopenfilename(
            title="选择 .ewp 文件",
            filetypes=[("IAR 项目文件", "*.ewp"), ("所有文件", "*.*")],
        )
        if path:
            self.ewp_var.set(path)
            self._load_project()

    def _browse_dir(self):
        initial = self.proj.proj_dir if self.proj else ""
        path = filedialog.askdirectory(title="选择要添加的文件夹", initialdir=initial)
        if path:
            self.dir_var.set(path)
            if not self.group_name_var.get():
                self.group_name_var.set(os.path.basename(path))
            self._set_status(f"已选择目录: {path}")

    def _load_project(self):
        path = self.ewp_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("错误", f"文件不存在: {path}")
            return
        try:
            self.proj = EwpProject(path)
            self.root.title(f"ewptools - {os.path.basename(path)}")
            self._refresh_tree()
            self._set_status(f"已加载项目: {path}")
        except Exception as e:
            messagebox.showerror("解析失败", str(e))

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._group_paths = {}
        if self.proj:
            self._populate_tree("", self.proj.root, "")
            self._fit_tree_column_to_content()
            self._set_status(f"树已刷新: {os.path.basename(self.proj.ewp_path)}")
            self._update_tree_toggle_button()

    def _capture_tree_open_state(self):
        """抓取当前树节点展开状态，key 为 group path。"""
        state = {}

        def walk(item_id):
            group_path = self._group_paths.get(item_id)
            tags = self.tree.item(item_id, "tags")
            if group_path and "group" in tags:
                state[group_path] = bool(self.tree.item(item_id, "open"))
            for child in self.tree.get_children(item_id):
                walk(child)

        for root_id in self.tree.get_children(""):
            walk(root_id)
        return state

    def _refresh_tree_preserve_state(self):
        """刷新树并尽量保持原有展开/折叠状态。"""
        open_state = self._capture_tree_open_state()
        self.tree.delete(*self.tree.get_children())
        self._group_paths = {}
        if self.proj:
            self._populate_tree("", self.proj.root, "", open_state=open_state)
            self._fit_tree_column_to_content()
            self._set_status(f"树已刷新: {os.path.basename(self.proj.ewp_path)}")
            self._update_tree_toggle_button()

    def _fit_tree_column_to_content(self):
        """按当前内容自适应树列宽度，触发横向滚动。"""
        if not self.tree.winfo_exists():
            return

        base_font = tkfont.nametofont("TkDefaultFont")
        max_width = base_font.measure("分组 / 文件") + 40

        def walk(item_id: str):
            nonlocal max_width
            text = self.tree.item(item_id, "text") or ""
            # 预留层级缩进和图标空间
            width = base_font.measure(text) + 60
            if width > max_width:
                max_width = width
            for child_id in self.tree.get_children(item_id):
                walk(child_id)

        for root_id in self.tree.get_children(""):
            walk(root_id)

        # 限制最大宽度，防止极端路径导致体验异常。
        max_width = max(400, min(max_width, 5000))
        self.tree.column("#0", width=max_width, minwidth=220, stretch=False)

    def _populate_tree(self, parent_id: str, element: ET.Element, parent_path: str, open_state=None):
        for group in element.findall("group"):
            name_elem = group.find("name")
            name = name_elem.text if name_elem is not None else "<unnamed>"
            group_path = f"{parent_path}/{name}" if parent_path else name
            file_count = self._count_group_files_recursive(group)
            default_open = True
            if open_state is not None:
                default_open = open_state.get(group_path, False)
            gid = self.tree.insert(parent_id, tk.END, text=f"[Group] {name} ({file_count} 文件)", open=default_open, tags=("group",))
            self._group_paths[gid] = group_path

            for file_elem in group.findall("file"):
                fname = file_elem.find("name")
                if fname is not None and fname.text:
                    display = fname.text.replace("$PROJ_DIR$\\", "")
                    self.tree.insert(gid, tk.END, text=f"[File] {display}", tags=("file",))

            self._populate_tree(gid, group, group_path, open_state=open_state)

    def _count_group_files_recursive(self, group: ET.Element) -> int:
        """统计当前 group 及其所有子 group 的文件总数。"""
        total = len(group.findall("file"))
        for subgroup in group.findall("group"):
            total += self._count_group_files_recursive(subgroup)
        return total

    def _get_selected_group_path(self):
        sel = self.tree.selection()
        if not sel:
            return None
        item_id = sel[0]
        tags = self.tree.item(item_id, "tags")
        if "group" not in tags:
            item_id = self.tree.parent(item_id)
            if not item_id:
                return None
        return self._group_paths.get(item_id)

    def _set_tree_open_state(self, item_id: str, open_state: bool):
        self.tree.item(item_id, open=open_state)
        for child in self.tree.get_children(item_id):
            self._set_tree_open_state(child, open_state)

    def _get_group_item_ids(self):
        group_ids = []

        def walk(item_id):
            tags = self.tree.item(item_id, "tags")
            if "group" in tags:
                group_ids.append(item_id)
            for child in self.tree.get_children(item_id):
                walk(child)

        for root_id in self.tree.get_children(""):
            walk(root_id)
        return group_ids

    def _all_groups_expanded(self):
        group_ids = self._get_group_item_ids()
        if not group_ids:
            return False
        for item_id in group_ids:
            if not bool(self.tree.item(item_id, "open")):
                return False
        return True

    def _update_tree_toggle_button(self):
        if self._all_groups_expanded():
            self.tree_toggle_text.set("折叠全部")
        else:
            self.tree_toggle_text.set("展开全部")

    def _toggle_tree_expand_collapse(self):
        expand = not self._all_groups_expanded()
        for item_id in self.tree.get_children(""):
            self._set_tree_open_state(item_id, expand)
        if expand:
            self._set_status("已展开全部节点")
        else:
            self._set_status("已折叠全部节点")
        self._update_tree_toggle_button()

    def _parse_extensions(self):
        raw = self.ext_var.get().strip()
        if not raw:
            return DEFAULT_SOURCE_EXTENSIONS
        exts = set()
        for part in raw.replace(",", " ").split():
            token = part.strip()
            if token:
                exts.add(token if token.startswith(".") else f".{token}")
        if self.include_headers_var.get():
            exts.update(HEADER_FILE_EXTENSIONS)
        return exts

    def _add_directory(self):
        if not self.proj:
            messagebox.showwarning("提示", "请先加载 .ewp 项目文件")
            return

        dir_path = self.dir_var.get().strip()
        if not dir_path or not os.path.isdir(dir_path):
            messagebox.showwarning("提示", "请选择一个有效的文件夹")
            return

        group_name = self.group_name_var.get().strip() or None
        extensions = self._parse_extensions()
        recursive = self.recursive_var.get()

        parent_path = None
        if self.add_to_selected_var.get():
            parent_path = self._get_selected_group_path()
            if not parent_path:
                messagebox.showwarning("提示", "请在树中选择一个父 Group")
                return

        try:
            added_count = self.proj.add_directory(
                dir_path=dir_path,
                group_name=group_name,
                parent_group_path=parent_path,
                extensions=extensions,
                recursive=recursive,
            )

            include_added = 0
            if self.sync_include_path_var.get():
                include_added = self.proj.add_include_paths_from_directory(
                    base_dir=dir_path,
                    recursive=recursive,
                )

            self.proj.save()
            self._refresh_tree_preserve_state()
            messagebox.showinfo(
                "完成",
                f"文件夹已添加并保存\n"
                f"新增文件: {added_count}\n"
                f"新增 Include Path: {include_added}",
            )
            self._set_status(f"添加完成: 文件 {added_count}，Include Path {include_added}")
            self.dir_var.set("")
            self.group_name_var.set("")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _remove_selected(self):
        if not self.proj:
            messagebox.showwarning("提示", "请先加载 .ewp 项目文件")
            return

        group_path = self._get_selected_group_path()
        if not group_path:
            messagebox.showwarning("提示", "请在树中选择要删除的 Group")
            return

        if not messagebox.askyesno("确认删除", f"确定要删除 Group '{group_path}' 吗？"):
            return

        try:
            self.proj.remove_group(group_path)
            self.proj.save()
            self._refresh_tree_preserve_state()
            self._set_status(f"已删除 Group: {group_path}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _sync_include_path_only(self):
        if not self.proj:
            messagebox.showwarning("提示", "请先加载 .ewp 项目文件")
            return

        dir_path = self.dir_var.get().strip()
        if not dir_path or not os.path.isdir(dir_path):
            messagebox.showwarning("提示", "请选择一个有效的文件夹")
            return

        recursive = self.recursive_var.get()
        try:
            include_added = self.proj.add_include_paths_from_directory(
                base_dir=dir_path,
                recursive=recursive,
            )
            self.proj.save()
            messagebox.showinfo("完成", f"Include Path 已同步\n新增 Include Path: {include_added}")
            self._set_status(f"Include Path 同步完成: 新增 {include_added}")
        except Exception as e:
            messagebox.showerror("错误", str(e))


def _hide_console_window():
    """Hide console window when running GUI mode from console subsystem."""
    if os.name != "nt":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def run_gui(ewp_path: str = None):
    _hide_console_window()
    root = tk.Tk()
    try:
        # Improve scaling on high-DPI displays.
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    EwpToolsApp(root, ewp_path)
    root.mainloop()


def main():
    ewp_path = None
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".ewp"):
        ewp_path = sys.argv[1]
    run_gui(ewp_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
