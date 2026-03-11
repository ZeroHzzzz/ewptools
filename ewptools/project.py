"""Core project model for reading and editing IAR `.ewp` files."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from .constants import (
    DEFAULT_SOURCE_EXTENSIONS,
    HEADER_FILE_EXTENSIONS,
    IGNORED_DIRECTORIES,
    PROJ_DIR_PREFIX,
)


class EwpProject:
    """IAR `.ewp` project file operations."""

    def __init__(self, ewp_path: str):
        self.ewp_path = os.path.abspath(ewp_path)
        self.proj_dir = os.path.dirname(self.ewp_path)
        self.tree = ET.parse(self.ewp_path)
        self.root = self.tree.getroot()
        self.ewt_path = self._detect_ewt_path()
        self.ewt_tree = ET.parse(self.ewt_path) if self.ewt_path else None
        self.ewt_root = self.ewt_tree.getroot() if self.ewt_tree is not None else None

    def _detect_ewt_path(self) -> str | None:
        candidate = os.path.splitext(self.ewp_path)[0] + ".ewt"
        return candidate if os.path.isfile(candidate) else None

    def _write_xml_tree(self, tree: ET.ElementTree, path: str) -> None:
        ET.indent(tree, space="    ")
        tree.write(path, encoding="UTF-8", xml_declaration=True)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        content = content.replace(
            "<?xml version='1.0' encoding='UTF-8'?>",
            '<?xml version="1.0" encoding="UTF-8"?>',
        )
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)

    def save(self, output_path: str | None = None, save_ewt: bool = True) -> list[str]:
        path = output_path or self.ewp_path
        saved_paths = [path]
        self._write_xml_tree(self.tree, path)

        if save_ewt and output_path is None and self.ewt_tree is not None and self.ewt_path:
            self._write_xml_tree(self.ewt_tree, self.ewt_path)
            saved_paths.append(self.ewt_path)

        for saved in saved_paths:
            print(f"[OK] 已保存: {saved}")
        return saved_paths

    def _iter_structure_roots(self, sync_ewt: bool = True) -> list[ET.Element]:
        roots = [self.root]
        if sync_ewt and self.ewt_root is not None:
            roots.append(self.ewt_root)
        return roots

    def _resolve_parent_group(self, root: ET.Element, parent_group_path: str | None) -> ET.Element:
        parent = root
        if parent_group_path:
            for part in parent_group_path.strip("/").split("/"):
                parent = self._find_or_create_group(parent, part)
        return parent

    def _to_proj_dir_path(self, abs_path: str) -> str:
        try:
            rel = os.path.relpath(abs_path, self.proj_dir)
            return f"{PROJ_DIR_PREFIX}{rel}"
        except ValueError:
            return abs_path

    def _find_group(self, parent: ET.Element, group_name: str) -> ET.Element | None:
        for group in parent.findall("group"):
            name_elem = group.find("name")
            if name_elem is not None and name_elem.text == group_name:
                return group
        return None

    def _find_or_create_group(self, parent: ET.Element, group_name: str) -> ET.Element:
        existing = self._find_group(parent, group_name)
        if existing is not None:
            return existing
        group = ET.SubElement(parent, "group")
        name = ET.SubElement(group, "name")
        name.text = group_name
        return group

    def _get_existing_files(self, group: ET.Element) -> set[str]:
        files: set[str] = set()
        for file_elem in group.findall("file"):
            name_elem = file_elem.find("name")
            if name_elem is not None and name_elem.text:
                files.add(name_elem.text)
        return files

    def _add_file_to_group(self, group: ET.Element, proj_dir_path: str) -> bool:
        if proj_dir_path in self._get_existing_files(group):
            return False
        file_elem = ET.SubElement(group, "file")
        name_elem = ET.SubElement(file_elem, "name")
        name_elem.text = proj_dir_path
        return True

    def _find_or_create_compiler_include_option(self, config: ET.Element) -> ET.Element | None:
        icc_settings = None
        for settings in config.findall("settings"):
            name_elem = settings.find("name")
            if name_elem is not None and name_elem.text and name_elem.text.startswith("ICC"):
                icc_settings = settings
                data = settings.find("data")
                if data is None:
                    data = ET.SubElement(settings, "data")
                for option in data.findall("option"):
                    opt_name = option.find("name")
                    if opt_name is not None and opt_name.text in ("CCIncludePath2", "CCIncludePath"):
                        return option

        if icc_settings is None:
            return None

        data = icc_settings.find("data")
        if data is None:
            data = ET.SubElement(icc_settings, "data")

        option = ET.SubElement(data, "option")
        option_name = ET.SubElement(option, "name")
        option_name.text = "CCIncludePath2"
        return option

    def _normalize_proj_path(self, path_value: str) -> str:
        return path_value.replace("/", "\\").rstrip("\\") if path_value else ""

    def _from_proj_dir_path(self, path_value: str) -> str:
        if not path_value:
            return ""
        value = path_value.replace("/", "\\")
        if value.startswith(PROJ_DIR_PREFIX):
            rel = value[len(PROJ_DIR_PREFIX):]
            return os.path.abspath(os.path.join(self.proj_dir, rel))
        return os.path.abspath(value)

    def _collect_include_dirs(self, base_dir: str, recursive: bool = True) -> list[str]:
        base_dir = os.path.abspath(base_dir)
        include_dirs: set[str] = set()

        for root, dirs, files in os.walk(base_dir):
            if not recursive:
                dirs[:] = []
            else:
                dirs[:] = [name for name in dirs if not name.startswith(".") and name not in IGNORED_DIRECTORIES]

            if any(os.path.splitext(name)[1].lower() in HEADER_FILE_EXTENSIONS for name in files):
                include_dirs.add(self._to_proj_dir_path(root))

        return sorted(include_dirs)

    def _add_include_dirs(self, include_dirs: list[str]) -> int:
        if not include_dirs:
            return 0

        added_count = 0
        for config in self.root.findall("configuration"):
            option = self._find_or_create_compiler_include_option(config)
            if option is None:
                continue

            existing = {self._normalize_proj_path(state.text or "") for state in option.findall("state")}
            for inc_dir in include_dirs:
                norm = self._normalize_proj_path(inc_dir)
                if norm in existing:
                    continue
                state = ET.SubElement(option, "state")
                state.text = inc_dir
                existing.add(norm)
                added_count += 1

        return added_count

    def add_include_paths_from_directory(self, base_dir: str, recursive: bool = True) -> int:
        return self._add_include_dirs(self._collect_include_dirs(base_dir, recursive=recursive))

    def add_include_paths_from_files(self, file_paths: list[str]) -> int:
        include_dirs: set[str] = set()
        for file_path in file_paths:
            if not file_path:
                continue
            parent = os.path.dirname(os.path.abspath(file_path))
            if parent and os.path.isdir(parent):
                include_dirs.add(self._to_proj_dir_path(parent))
        return self._add_include_dirs(sorted(include_dirs))

    def add_directory(
        self,
        dir_path: str,
        group_name: str | None = None,
        parent_group_path: str | None = None,
        extensions: set[str] | None = None,
        recursive: bool = True,
        sync_ewt: bool = True,
    ) -> int:
        dir_path = os.path.abspath(dir_path)
        if not os.path.isdir(dir_path):
            print(f"[错误] 目录不存在: {dir_path}")
            return 0

        extensions = extensions or DEFAULT_SOURCE_EXTENSIONS
        group_name = group_name or os.path.basename(dir_path)

        parent = self._resolve_parent_group(self.root, parent_group_path)
        added_count = self._add_dir_recursive(parent, dir_path, group_name, extensions, recursive)

        for mirror_root in self._iter_structure_roots(sync_ewt=sync_ewt)[1:]:
            mirror_parent = self._resolve_parent_group(mirror_root, parent_group_path)
            self._add_dir_recursive(mirror_parent, dir_path, group_name, extensions, recursive)

        print(f"[OK] 已添加 {added_count} 个文件到 group '{group_name}'")
        return added_count

    def _add_dir_recursive(
        self,
        parent: ET.Element,
        dir_path: str,
        group_name: str,
        extensions: set[str],
        recursive: bool,
    ) -> int:
        group = self._find_or_create_group(parent, group_name)
        added = 0

        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            print(f"[警告] 无权访问: {dir_path}")
            return 0

        for entry in entries:
            full_path = os.path.join(dir_path, entry)
            if os.path.isfile(full_path) and os.path.splitext(entry)[1].lower() in extensions:
                proj_path = self._to_proj_dir_path(full_path)
                if self._add_file_to_group(group, proj_path):
                    added += 1

        if recursive:
            for entry in entries:
                full_path = os.path.join(dir_path, entry)
                if not os.path.isdir(full_path):
                    continue
                if entry.startswith(".") or entry in IGNORED_DIRECTORIES:
                    continue
                added += self._add_dir_recursive(group, full_path, entry, extensions, recursive)

        return added

    def _add_files_to_root(
        self,
        root: ET.Element,
        file_paths: list[str],
        parent_group_path: str | None = None,
        group_name: str | None = None,
    ) -> int:
        parent = self._resolve_parent_group(root, parent_group_path)

        if group_name:
            target_group = self._find_or_create_group(parent, group_name)
        elif parent.tag == "group":
            target_group = parent
        else:
            target_group = self._find_or_create_group(parent, "files")

        added = 0
        for path in file_paths:
            if not os.path.isfile(path):
                continue
            proj_path = self._to_proj_dir_path(os.path.abspath(path))
            if self._add_file_to_group(target_group, proj_path):
                added += 1
        return added

    def _collect_group_files(self, group: ET.Element) -> list[str]:
        files: list[str] = []
        for file_elem in group.findall("file"):
            name_elem = file_elem.find("name")
            if name_elem is not None and name_elem.text:
                files.append(name_elem.text)
        for child in group.findall("group"):
            files.extend(self._collect_group_files(child))
        return files

    def _find_group_by_parts(self, root: ET.Element, parts: list[str]) -> ET.Element | None:
        node = root
        for part in parts:
            node = self._find_group(node, part)
            if node is None:
                return None
        return node

    def _collect_all_project_file_paths(self, root: ET.Element | None = None) -> list[str]:
        current_root = root or self.root
        files: list[str] = []
        for group in current_root.findall("group"):
            files.extend(self._collect_group_files(group))
        return files

    def remove_include_paths_for_files(self, removed_file_paths: list[str]) -> int:
        if not removed_file_paths:
            return 0

        remaining = self._collect_all_project_file_paths(self.root)
        remaining_dirs = {self._normalize_proj_path(os.path.dirname(path)) for path in remaining if path}
        candidate_dirs = {self._normalize_proj_path(os.path.dirname(path)) for path in removed_file_paths if path}
        stale_dirs = candidate_dirs - remaining_dirs
        if not stale_dirs:
            return 0

        removed_count = 0
        for config in self.root.findall("configuration"):
            option = self._find_or_create_compiler_include_option(config)
            if option is None:
                continue
            for state in list(option.findall("state")):
                value = self._normalize_proj_path(state.text or "")
                if value in stale_dirs:
                    option.remove(state)
                    removed_count += 1
        return removed_count

    def add_files(
        self,
        file_paths: list[str],
        parent_group_path: str | None = None,
        group_name: str | None = None,
        sync_ewt: bool = True,
    ) -> int:
        valid_files = [os.path.abspath(path) for path in file_paths if os.path.isfile(path)]
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

    def _remove_group_in_root(self, root: ET.Element, parts: list[str]) -> bool:
        parent = root
        for index, part in enumerate(parts):
            if index == len(parts) - 1:
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

    def remove_group(self, group_path: str, sync_ewt: bool = True) -> list[str]:
        parts = group_path.strip("/").split("/")
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
        for group in root.findall("group"):
            for file_elem in list(group.findall("file")):
                name_elem = file_elem.find("name")
                if name_elem is not None and (name_elem.text or "") == file_path:
                    group.remove(file_elem)
                    return True

            if self._remove_file_in_root(group, file_path):
                return True

        return False

    def remove_file(self, file_path: str, sync_ewt: bool = True) -> list[str]:
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
