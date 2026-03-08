"""ewptools GUI - IAR Embedded Workbench (.ewp) 项目文件管理工具。"""

import xml.etree.ElementTree as ET
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText


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
        self.ewt_path = self._detect_ewt_path()
        self.ewt_tree = ET.parse(self.ewt_path) if self.ewt_path else None
        self.ewt_root = self.ewt_tree.getroot() if self.ewt_tree is not None else None

    def _detect_ewt_path(self) -> str:
        """自动匹配与 .ewp 同名的 .ewt 文件。"""
        candidate = os.path.splitext(self.ewp_path)[0] + '.ewt'
        if os.path.isfile(candidate):
            return candidate
        return None

    def _write_xml_tree(self, tree: ET.ElementTree, path: str):
        """统一写 XML，修正声明格式为 IAR 常用双引号风格。"""
        ET.indent(tree, space="    ")
        tree.write(path, encoding="UTF-8", xml_declaration=True)
        # ET.write 写的是 <?xml version='1.0' encoding='UTF-8'?>（单引号）
        # IAR 使用双引号，这里做一个替换以保持兼容
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace("<?xml version='1.0' encoding='UTF-8'?>",
                                  '<?xml version="1.0" encoding="UTF-8"?>')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def save(self, output_path: str = None, save_ewt: bool = True):
        """保存 .ewp 文件；按需保存同名 .ewt。"""
        path = output_path or self.ewp_path
        saved_paths = []

        self._write_xml_tree(self.tree, path)
        saved_paths.append(path)

        # output_path 场景下只允许覆盖当前 .ewp 路径，避免误写 .ewt 到未知位置。
        if save_ewt and output_path is None and self.ewt_tree is not None and self.ewt_path:
            self._write_xml_tree(self.ewt_tree, self.ewt_path)
            saved_paths.append(self.ewt_path)

        for saved in saved_paths:
            print(f"[OK] 已保存: {saved}")
        return saved_paths

    def _iter_structure_roots(self, sync_ewt: bool = True):
        """返回需要同步 group/file 结构的 XML 根节点列表。"""
        roots = [self.root]
        if sync_ewt and self.ewt_root is not None:
            roots.append(self.ewt_root)
        return roots

    def _resolve_parent_group(self, root: ET.Element, parent_group_path: str) -> ET.Element:
        """按路径在指定 root 下定位(或创建)父 group。"""
        parent = root
        if parent_group_path:
            parts = parent_group_path.strip('/').split('/')
            for part in parts:
                parent = self._find_or_create_group(parent, part)
        return parent

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

    def _from_proj_dir_path(self, path_value: str) -> str:
        """将 $PROJ_DIR$ 路径解析为绝对路径。"""
        if not path_value:
            return ''

        value = path_value.replace('/', '\\')
        prefix = '$PROJ_DIR$\\'
        if value.startswith(prefix):
            rel = value[len(prefix):]
            return os.path.abspath(os.path.join(self.proj_dir, rel))
        return os.path.abspath(value)

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

    def _add_include_dirs(self, include_dirs: list) -> int:
        """将目录列表追加到各配置的编译器 Include Path。"""
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

    def add_include_paths_from_directory(self, base_dir: str, recursive: bool = True):
        """将目录中发现的头文件目录追加到各配置的编译器 Include Path。"""
        include_dirs = self._collect_include_dirs(base_dir, recursive=recursive)
        return self._add_include_dirs(include_dirs)

    def add_include_paths_from_files(self, file_paths: list) -> int:
        """根据文件路径列表，将其所在目录追加到 Include Path。"""
        include_dirs = set()
        for file_path in file_paths:
            if not file_path:
                continue
            abs_path = os.path.abspath(file_path)
            parent = os.path.dirname(abs_path)
            if parent and os.path.isdir(parent):
                include_dirs.add(self._to_proj_dir_path(parent))

        return self._add_include_dirs(sorted(include_dirs))

    def add_directory(self, dir_path: str, group_name: str = None,
                      parent_group_path: str = None,
                      extensions: set = None, recursive: bool = True,
                      sync_ewt: bool = True):
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

        # 先改 .ewp，统计新增数量；若存在 .ewt 再做结构镜像同步。
        parent = self._resolve_parent_group(self.root, parent_group_path)
        added_count = self._add_dir_recursive(parent, dir_path, group_name, extensions, recursive)

        for mirror_root in self._iter_structure_roots(sync_ewt=sync_ewt)[1:]:
            mirror_parent = self._resolve_parent_group(mirror_root, parent_group_path)
            self._add_dir_recursive(mirror_parent, dir_path, group_name, extensions, recursive)

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

    def _add_files_to_root(self, root: ET.Element, file_paths: list,
                           parent_group_path: str = None,
                           group_name: str = None) -> int:
        """在指定 root 下添加文件条目。"""
        parent = self._resolve_parent_group(root, parent_group_path)
        added = 0

        target_group = None
        if group_name:
            target_group = self._find_or_create_group(parent, group_name)
        elif parent.tag == 'group':
            target_group = parent
        else:
            # 顶层未指定 group 时，使用统一分组，避免按文件目录自动分组。
            target_group = self._find_or_create_group(parent, 'files')

        for path in file_paths:
            if not os.path.isfile(path):
                continue

            proj_path = self._to_proj_dir_path(os.path.abspath(path))
            if self._add_file_to_group(target_group, proj_path):
                added += 1

        return added

    def _collect_group_files(self, group: ET.Element) -> list:
        """收集 group 及其子 group 的 file/name 路径。"""
        files = []
        for file_elem in group.findall('file'):
            name_elem = file_elem.find('name')
            if name_elem is not None and name_elem.text:
                files.append(name_elem.text)

        for child in group.findall('group'):
            files.extend(self._collect_group_files(child))

        return files

    def _find_group_by_parts(self, root: ET.Element, parts: list) -> ET.Element:
        """按路径 parts 查找 group。"""
        node = root
        for part in parts:
            node = self._find_group(node, part)
            if node is None:
                return None
        return node

    def _collect_all_project_file_paths(self, root: ET.Element = None) -> list:
        """收集工程中全部 file/name 路径。"""
        if root is None:
            root = self.root

        files = []
        for group in root.findall('group'):
            files.extend(self._collect_group_files(group))
        return files

    def remove_include_paths_for_files(self, removed_file_paths: list) -> int:
        """根据已删除文件列表，清理不再被工程引用的 Include Path。"""
        if not removed_file_paths:
            return 0

        remaining = self._collect_all_project_file_paths(self.root)
        remaining_dirs = {self._normalize_proj_path(os.path.dirname(p)) for p in remaining if p}

        candidate_dirs = set()
        for path in removed_file_paths:
            if not path:
                continue
            candidate_dirs.add(self._normalize_proj_path(os.path.dirname(path)))

        stale_dirs = candidate_dirs - remaining_dirs
        if not stale_dirs:
            return 0

        removed_count = 0
        for config in self.root.findall('configuration'):
            option = self._find_or_create_compiler_include_option(config)
            if option is None:
                continue

            for state in list(option.findall('state')):
                value = self._normalize_proj_path(state.text or '')
                if value in stale_dirs:
                    option.remove(state)
                    removed_count += 1

        return removed_count

    def add_files(self, file_paths: list,
                  parent_group_path: str = None,
                  group_name: str = None,
                  sync_ewt: bool = True) -> int:
        """添加一个或多个文件到工程结构中。"""
        valid_files = [os.path.abspath(p) for p in file_paths if os.path.isfile(p)]
        if not valid_files:
            print("[错误] 未提供有效文件")
            return 0

        added_count = self._add_files_to_root(
            self.root,
            valid_files,
            parent_group_path=parent_group_path,
            group_name=group_name,
        )

        for mirror_root in self._iter_structure_roots(sync_ewt=sync_ewt)[1:]:
            self._add_files_to_root(
                mirror_root,
                valid_files,
                parent_group_path=parent_group_path,
                group_name=group_name,
            )

        print(f"[OK] 已添加 {added_count} 个文件")
        return added_count

    def _remove_group_in_root(self, root: ET.Element, parts: list) -> bool:
        """在指定 root 下删除 group，成功返回 True。"""
        parent = root
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                target = self._find_group(parent, part)
                if target is None:
                    return False
                parent.remove(target)
                return True

            next_parent = self._find_group(parent, part)
            if next_parent is None:
                return False
            parent = next_parent
        return False

    def remove_group(self, group_path: str, sync_ewt: bool = True):
        """
        删除指定路径的 group。

        Args:
            group_path: group 路径，用 '/' 分隔，如 "Source/Drivers"
        """
        parts = group_path.strip('/').split('/')
        if not parts:
            print("[错误] group 路径不能为空")
            return []

        target_group = self._find_group_by_parts(self.root, parts)
        removed_files = self._collect_group_files(target_group) if target_group is not None else []

        if not self._remove_group_in_root(self.root, parts):
            print(f"[错误] 未找到 group: {group_path}")
            return []

        for mirror_root in self._iter_structure_roots(sync_ewt=sync_ewt)[1:]:
            self._remove_group_in_root(mirror_root, parts)

        print(f"[OK] 已删除 group: {group_path}")
        return removed_files

    def _remove_file_in_root(self, root: ET.Element, file_path: str) -> bool:
        """在指定 root 下删除一个文件节点，成功返回 True。"""
        for group in root.findall('group'):
            for file_elem in list(group.findall('file')):
                name_elem = file_elem.find('name')
                if name_elem is not None and (name_elem.text or '') == file_path:
                    group.remove(file_elem)
                    return True

            if self._remove_file_in_root(group, file_path):
                return True

        return False

    def remove_file(self, file_path: str, sync_ewt: bool = True) -> list:
        """删除工程结构中的一个文件条目（不删除磁盘文件）。"""
        if not file_path:
            print("[错误] 文件路径不能为空")
            return []

        if not self._remove_file_in_root(self.root, file_path):
            print(f"[错误] 未找到文件: {file_path}")
            return []

        for mirror_root in self._iter_structure_roots(sync_ewt=sync_ewt)[1:]:
            self._remove_file_in_root(mirror_root, file_path)

        print(f"[OK] 已删除文件: {file_path}")
        return [file_path]

class EwpToolsApp:
    """Tkinter GUI for managing .ewp project groups/files."""

    def __init__(self, root: tk.Tk, ewp_path: str = None):
        self.root = root
        self.root.title("ewptools - IAR 项目管理")
        self.root.geometry("980x640")
        self.root.minsize(600, 450)

        self.proj: EwpProject = None
        self._group_paths = {}
        self._file_paths = {}

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
        self.ext_var = tk.StringVar(value=".c .cpp .cxx .cc .s .asm .icf .inc")
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

        ttk.Button(action_frame, text="添加路径（文件/目录）", command=self._add_paths).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        ttk.Button(action_frame, text="仅同步 Include Path", command=self._sync_include_path_only).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        ttk.Button(action_frame, text="删除选中项", command=self._remove_selected).grid(row=6, column=0, columnspan=3, sticky="ew")

        self.status_var = tk.StringVar(value="未加载项目")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W)
        status.pack(fill=tk.X, padx=10, pady=(0, 8))

        log_frame = ttk.LabelFrame(self.root, text="日志", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(log_toolbar, text="清空日志", command=self._clear_log).pack(side=tk.RIGHT)

        self.log_text = ScrolledText(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _log(self, text: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{text}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _ok(self, text: str):
        self._set_status(text)
        self._log(f"[OK] {text}")

    def _warn(self, text: str):
        self._set_status(text)
        self._log(f"[WARN] {text}")

    def _err(self, text: str, exc: Exception = None):
        msg = f"{text}: {exc}" if exc is not None else text
        self._set_status(msg)
        self._log(f"[ERR] {msg}")
        messagebox.showerror("错误", msg)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _save_and_refresh(self, sync_ewt: bool):
        saved_paths = self.proj.save(save_ewt=sync_ewt)
        self._refresh_tree_preserve_state()
        for path in saved_paths:
            self._log(f"[SAVE] {path}")
        return saved_paths

    def _sel_parent_group(self):
        parent_path = None
        if self.add_to_selected_var.get():
            parent_path = self._get_selected_group_path()
            if not parent_path:
                messagebox.showwarning("提示", "请在树中选择一个父 Group")
                return None
        return parent_path

    def _reset_default_extensions(self):
        self.ext_var.set(".c .cpp .cxx .cc .s .asm .icf .inc")
        self.include_headers_var.set(True)
        self._ok("已恢复推荐扩展名，并启用包含头文件")

    def _browse_ewp(self):
        path = filedialog.askopenfilename(
            title="选择 .ewp 文件",
            filetypes=[("IAR 项目文件", "*.ewp"), ("所有文件", "*.*")],
        )
        if path:
            self.ewp_var.set(path)
            self._load_project()

    def _pick_dirs(self):
        """文件夹选择入口：单次选择一个目录并追加。"""
        initial = self.proj.proj_dir if self.proj else ""
        path = filedialog.askdirectory(title="选择文件夹", initialdir=initial)
        if path:
            self._set_path_list([path], append=True)
            self._ok("已选择文件夹: 1")

    def _pick_files(self):
        """文件选择入口：支持单次多选文件。"""
        initial = self.proj.proj_dir if self.proj else ""
        files = filedialog.askopenfilenames(
            title="选择文件（可多选）",
            initialdir=initial,
            filetypes=[("所有文件", "*.*")],
        )
        if files:
            self._set_path_list(list(files), append=True)
            self._ok(f"已选择文件: {len(files)}")

    def _parse_input_paths(self):
        """将输入框中的路径文本解析为路径列表（支持分号和换行分隔）。"""
        raw = self.dir_var.get().strip()
        if not raw:
            return []

        normalized = raw.replace('\r\n', '\n').replace('\r', '\n').replace('\n', ';')
        paths = []
        for part in normalized.split(';'):
            item = part.strip().strip('"')
            if item:
                paths.append(item)

        # 去重并保持顺序
        unique = []
        seen = set()
        for p in paths:
            np = os.path.normpath(p)
            if np not in seen:
                seen.add(np)
                unique.append(np)
        return unique

    def _set_path_list(self, paths, append: bool):
        """设置/追加路径输入框内容，使用分号连接。"""
        current = self._parse_input_paths() if append else []
        merged = current + [os.path.normpath(p) for p in paths if p]

        unique = []
        seen = set()
        for p in merged:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        self.dir_var.set(';'.join(unique))

    def _load_project(self):
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
        except Exception as e:
            self._err("解析失败", e)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._group_paths = {}
        self._file_paths = {}
        if self.proj:
            self._populate_tree("", self.proj.root, "")
            self._fit_tree_column_to_content()
            self._ok(f"树已刷新: {os.path.basename(self.proj.ewp_path)}")
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
        self._file_paths = {}
        if self.proj:
            self._populate_tree("", self.proj.root, "", open_state=open_state)
            self._fit_tree_column_to_content()
            self._ok(f"树已刷新: {os.path.basename(self.proj.ewp_path)}")
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
                    fid = self.tree.insert(gid, tk.END, text=f"[File] {display}", tags=("file",))
                    self._file_paths[fid] = fname.text

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

    def _get_selected_item(self):
        """返回当前选中项信息：('group'|'file', path, tree_id)。"""
        sel = self.tree.selection()
        if not sel:
            return None, None, None

        item_id = sel[0]
        tags = self.tree.item(item_id, "tags")
        if "group" in tags:
            return "group", self._group_paths.get(item_id), item_id
        if "file" in tags:
            return "file", self._file_paths.get(item_id), item_id

        return None, None, item_id

    def _should_sync_ewt(self) -> bool:
        """根据用户开关和项目状态决定是否同步 .ewt。"""
        if not self.sync_ewt_var.get():
            return False
        if not self.proj or not self.proj.ewt_path:
            return False
        return True

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
            self._ok("已展开全部节点")
        else:
            self._ok("已折叠全部节点")
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

    def _add_paths(self):
        if not self.proj:
            messagebox.showwarning("提示", "请先加载 .ewp 项目文件")
            return

        input_paths = self._parse_input_paths()
        dir_paths = [p for p in input_paths if os.path.isdir(p)]
        file_paths = [p for p in input_paths if os.path.isfile(p)]
        if not dir_paths and not file_paths:
            messagebox.showwarning("提示", "请至少选择一个有效路径（文件或目录，可用分号分隔）")
            return

        group_name = self.group_name_var.get().strip() or None
        extensions = self._parse_extensions()
        recursive = self.recursive_var.get()

        parent_path = self._sel_parent_group()
        if self.add_to_selected_var.get() and parent_path is None:
            return

        try:
            sync_ewt = self._should_sync_ewt()
            added_dir_files = 0
            added_files = 0
            include_added = 0

            for dir_path in dir_paths:
                current_group_name = group_name if (len(dir_paths) == 1 and group_name) else os.path.basename(dir_path)
                added_dir_files += self.proj.add_directory(
                    dir_path=dir_path,
                    group_name=current_group_name,
                    parent_group_path=parent_path,
                    extensions=extensions,
                    recursive=recursive,
                    sync_ewt=sync_ewt,
                )

                if self.sync_include_path_var.get():
                    include_added += self.proj.add_include_paths_from_directory(
                        base_dir=dir_path,
                        recursive=recursive,
                    )

            if file_paths:
                added_files = self.proj.add_files(
                    file_paths=file_paths,
                    parent_group_path=parent_path,
                    group_name=group_name,
                    sync_ewt=sync_ewt,
                )
                if self.sync_include_path_var.get():
                    include_added += self.proj.add_include_paths_from_files(file_paths)

            saved_paths = self._save_and_refresh(sync_ewt)
            self._ok(
                f"路径添加完成: 目录 {len(dir_paths)}，目录新增文件 {added_dir_files}，"
                f"文件条目新增 {added_files}，Include Path {include_added}，保存 {len(saved_paths)} 个文件"
            )
            self.dir_var.set("")
            self.group_name_var.set("")
        except Exception as e:
            self._err("添加路径失败", e)

    def _remove_selected(self):
        if not self.proj:
            messagebox.showwarning("提示", "请先加载 .ewp 项目文件")
            return

        item_type, item_path, _ = self._get_selected_item()
        if item_type not in ("group", "file") or not item_path:
            messagebox.showwarning("提示", "请在树中选择要删除的 Group 或 File")
            return

        if item_type == "group":
            prompt = f"确定要删除 Group '{item_path}' 吗？\n\n注意：仅删除工程结构，不删除磁盘文件。"
        else:
            prompt = f"确定要删除 File 条目 '{item_path}' 吗？\n\n注意：仅删除工程结构，不删除磁盘文件。"

        if not messagebox.askyesno("确认删除", prompt):
            return

        try:
            sync_ewt = self._should_sync_ewt()
            removed_files = []
            if item_type == "group":
                removed_files = self.proj.remove_group(item_path, sync_ewt=sync_ewt)
                action_text = f"已删除 Group: {item_path}"
            else:
                removed_files = self.proj.remove_file(item_path, sync_ewt=sync_ewt)
                if not removed_files:
                    messagebox.showerror("错误", f"未找到 File 条目: {item_path}")
                    return
                action_text = f"已删除 File: {item_path}"

            include_removed = 0
            if self.sync_include_path_var.get() and removed_files:
                include_removed = self.proj.remove_include_paths_for_files(removed_files)

            saved_paths = self._save_and_refresh(sync_ewt)
            self._ok(f"{action_text}，清理 Include Path {include_removed} 条，保存 {len(saved_paths)} 个文件")
        except Exception as e:
            self._err("删除失败", e)

    def _sync_include_path_only(self):
        if not self.proj:
            messagebox.showwarning("提示", "请先加载 .ewp 项目文件")
            return

        input_paths = self._parse_input_paths()
        dir_paths = [p for p in input_paths if os.path.isdir(p)]
        if not dir_paths:
            messagebox.showwarning("提示", "请至少选择一个有效文件夹")
            return

        recursive = self.recursive_var.get()
        try:
            sync_ewt = self._should_sync_ewt()
            include_added = 0
            for dir_path in dir_paths:
                include_added += self.proj.add_include_paths_from_directory(
                    base_dir=dir_path,
                    recursive=recursive,
                )
            saved_paths = self._save_and_refresh(sync_ewt)
            self._ok(f"Include Path 同步完成: 新增 {include_added}，保存 {len(saved_paths)} 个文件")
        except Exception as e:
            self._err("Include Path 同步失败", e)


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
