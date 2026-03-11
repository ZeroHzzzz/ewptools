"""Treeview presentation layer for project groups and files."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal
from tkinter import ttk


@dataclass(frozen=True)
class TreeSelection:
    item_type: Literal["group", "file"] | None
    path: str | None
    tree_id: str | None


class ProjectTreeController:
    """Encapsulates tree rendering, selection lookup, and open-state handling."""

    def __init__(self, tree: ttk.Treeview, toggle_text: tk.StringVar):
        self.tree = tree
        self.toggle_text = toggle_text
        self._group_paths: dict[str, str] = {}
        self._file_paths: dict[str, str] = {}

    def refresh(self, root_element: ET.Element, preserve_state: bool = False) -> None:
        open_state = self._capture_tree_open_state() if preserve_state else None
        self.tree.delete(*self.tree.get_children())
        self._group_paths.clear()
        self._file_paths.clear()
        self._populate_tree("", root_element, "", open_state=open_state)
        self._fit_column_to_content()
        self.update_toggle_button()

    def selected_group_path(self) -> str | None:
        selection = self.tree.selection()
        if not selection:
            return None
        item_id = selection[0]
        tags = self.tree.item(item_id, "tags")
        if "group" not in tags:
            item_id = self.tree.parent(item_id)
            if not item_id:
                return None
        return self._group_paths.get(item_id)

    def selected_item(self) -> TreeSelection:
        selection = self.tree.selection()
        if not selection:
            return TreeSelection(None, None, None)

        item_id = selection[0]
        tags = self.tree.item(item_id, "tags")
        if "group" in tags:
            return TreeSelection("group", self._group_paths.get(item_id), item_id)
        if "file" in tags:
            return TreeSelection("file", self._file_paths.get(item_id), item_id)
        return TreeSelection(None, None, item_id)

    def toggle_expand_collapse(self) -> bool:
        expand = not self.all_groups_expanded()
        for item_id in self.tree.get_children(""):
            self._set_tree_open_state(item_id, expand)
        self.update_toggle_button()
        return expand

    def update_toggle_button(self) -> None:
        self.toggle_text.set("折叠全部" if self.all_groups_expanded() else "展开全部")

    def all_groups_expanded(self) -> bool:
        group_ids = self._get_group_item_ids()
        return bool(group_ids) and all(bool(self.tree.item(item_id, "open")) for item_id in group_ids)

    def _capture_tree_open_state(self) -> dict[str, bool]:
        state: dict[str, bool] = {}

        def walk(item_id: str) -> None:
            group_path = self._group_paths.get(item_id)
            tags = self.tree.item(item_id, "tags")
            if group_path and "group" in tags:
                state[group_path] = bool(self.tree.item(item_id, "open"))
            for child in self.tree.get_children(item_id):
                walk(child)

        for root_id in self.tree.get_children(""):
            walk(root_id)
        return state

    def _fit_column_to_content(self) -> None:
        if not self.tree.winfo_exists():
            return

        base_font = tkfont.nametofont("TkDefaultFont")
        max_width = base_font.measure("分组 / 文件") + 40

        def walk(item_id: str) -> None:
            nonlocal max_width
            text = self.tree.item(item_id, "text") or ""
            width = base_font.measure(text) + 60
            if width > max_width:
                max_width = width
            for child_id in self.tree.get_children(item_id):
                walk(child_id)

        for root_id in self.tree.get_children(""):
            walk(root_id)

        self.tree.column("#0", width=max(400, min(max_width, 5000)), minwidth=220, stretch=False)

    def _populate_tree(
        self,
        parent_id: str,
        element: ET.Element,
        parent_path: str,
        open_state: dict[str, bool] | None = None,
    ) -> None:
        for group in element.findall("group"):
            name_elem = group.find("name")
            name = name_elem.text if name_elem is not None else "<unnamed>"
            group_path = f"{parent_path}/{name}" if parent_path else name
            file_count = self._count_group_files_recursive(group)
            default_open = True if open_state is None else open_state.get(group_path, False)
            group_id = self.tree.insert(
                parent_id,
                tk.END,
                text=f"[Group] {name} ({file_count} 文件)",
                open=default_open,
                tags=("group",),
            )
            self._group_paths[group_id] = group_path

            for file_elem in group.findall("file"):
                name_node = file_elem.find("name")
                if name_node is None or not name_node.text:
                    continue
                display = name_node.text.replace("$PROJ_DIR$\\", "")
                file_id = self.tree.insert(group_id, tk.END, text=f"[File] {display}", tags=("file",))
                self._file_paths[file_id] = name_node.text

            self._populate_tree(group_id, group, group_path, open_state=open_state)

    def _count_group_files_recursive(self, group: ET.Element) -> int:
        total = len(group.findall("file"))
        for subgroup in group.findall("group"):
            total += self._count_group_files_recursive(subgroup)
        return total

    def _set_tree_open_state(self, item_id: str, open_state: bool) -> None:
        self.tree.item(item_id, open=open_state)
        for child in self.tree.get_children(item_id):
            self._set_tree_open_state(child, open_state)

    def _get_group_item_ids(self) -> list[str]:
        group_ids: list[str] = []

        def walk(item_id: str) -> None:
            if "group" in self.tree.item(item_id, "tags"):
                group_ids.append(item_id)
            for child in self.tree.get_children(item_id):
                walk(child)

        for root_id in self.tree.get_children(""):
            walk(root_id)
        return group_ids
