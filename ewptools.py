"""ewptools GUI - IAR Embedded Workbench (.ewp) 项目文件管理工具。"""

import xml.etree.ElementTree as ET
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# 常见的 IAR 项目源文件扩展名
DEFAULT_SOURCE_EXTENSIONS = {
    '.c', '.h', '.cpp', '.hpp', '.cxx', '.cc',
    '.s', '.asm', '.S',
    '.icf',  # linker script
    '.inc',
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
        self.root.geometry("750x600")
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
        ewp_entry = ttk.Entry(top_frame, textvariable=self.ewp_var, width=60)
        ewp_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        ttk.Button(top_frame, text="浏览...", command=self._browse_ewp).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top_frame, text="加载", command=self._load_project).pack(side=tk.LEFT)

        tree_frame = ttk.LabelFrame(self.root, text="项目结构", padding=8)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(tree_frame, yscrollcommand=tree_scroll.set, selectmode="browse")
        tree_scroll.config(command=self.tree.yview)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.heading("#0", text="Group / File", anchor=tk.W)

        action_frame = ttk.LabelFrame(self.root, text="添加文件夹", padding=8)
        action_frame.pack(fill=tk.X, padx=8, pady=(4, 8))

        row1 = ttk.Frame(action_frame)
        row1.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row1, text="目录:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.dir_var, width=45).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row1, text="选择...", command=self._browse_dir).pack(side=tk.LEFT)

        row2 = ttk.Frame(action_frame)
        row2.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row2, text="Group 名:").pack(side=tk.LEFT)
        self.group_name_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.group_name_var, width=20).pack(side=tk.LEFT, padx=4)

        ttk.Label(row2, text="扩展名:").pack(side=tk.LEFT, padx=(12, 0))
        self.ext_var = tk.StringVar(value=".c .h .cpp .hpp .s .asm .icf")
        ttk.Entry(row2, textvariable=self.ext_var, width=30).pack(side=tk.LEFT, padx=4)

        row3 = ttk.Frame(action_frame)
        row3.pack(fill=tk.X)

        self.recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text="递归子目录", variable=self.recursive_var).pack(side=tk.LEFT)

        self.add_to_selected_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="添加到选中的 Group 下", variable=self.add_to_selected_var).pack(side=tk.LEFT, padx=12)

        btn_frame = ttk.Frame(row3)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="删除选中 Group", command=self._remove_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="添加文件夹", command=self._add_directory).pack(side=tk.LEFT, padx=4)

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

    def _load_project(self):
        path = self.ewp_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("错误", f"文件不存在: {path}")
            return
        try:
            self.proj = EwpProject(path)
            self.root.title(f"ewptools - {os.path.basename(path)}")
            self._refresh_tree()
        except Exception as e:
            messagebox.showerror("解析失败", str(e))

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._group_paths = {}
        if self.proj:
            self._populate_tree("", self.proj.root, "")

    def _populate_tree(self, parent_id: str, element: ET.Element, parent_path: str):
        for group in element.findall("group"):
            name_elem = group.find("name")
            name = name_elem.text if name_elem is not None else "<unnamed>"
            group_path = f"{parent_path}/{name}" if parent_path else name
            file_count = len(group.findall("file"))
            gid = self.tree.insert(parent_id, tk.END, text=f"[Group] {name} ({file_count} 文件)", open=True, tags=("group",))
            self._group_paths[gid] = group_path

            for file_elem in group.findall("file"):
                fname = file_elem.find("name")
                if fname is not None and fname.text:
                    display = fname.text.replace("$PROJ_DIR$\\", "")
                    self.tree.insert(gid, tk.END, text=f"[File] {display}", tags=("file",))

            self._populate_tree(gid, group, group_path)

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

    def _parse_extensions(self):
        raw = self.ext_var.get().strip()
        if not raw:
            return DEFAULT_SOURCE_EXTENSIONS
        exts = set()
        for part in raw.replace(",", " ").split():
            token = part.strip()
            if token:
                exts.add(token if token.startswith(".") else f".{token}")
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
            self.proj.add_directory(
                dir_path=dir_path,
                group_name=group_name,
                parent_group_path=parent_path,
                extensions=extensions,
                recursive=recursive,
            )
            self.proj.save()
            self._refresh_tree()
            messagebox.showinfo("完成", "文件夹已添加并保存")
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
            self._refresh_tree()
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
