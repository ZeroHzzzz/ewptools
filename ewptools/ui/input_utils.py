"""Pure helpers for parsing user input."""

from __future__ import annotations

import os
from collections.abc import Sequence

from ewptools.constants import DEFAULT_EXTENSION_TEXT, DEFAULT_SOURCE_EXTENSIONS, HEADER_FILE_EXTENSIONS


def parse_input_paths(raw_text: str) -> list[str]:
    raw = raw_text.strip()
    if not raw:
        return []

    normalized = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\n", ";")
    paths: list[str] = []
    for part in normalized.split(";"):
        item = part.strip().strip('"')
        if item:
            paths.append(os.path.normpath(item))

    unique_paths: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique_paths.append(path)
    return unique_paths


def merge_input_paths(current_text: str, new_paths: Sequence[str], append: bool) -> str:
    current_paths = parse_input_paths(current_text) if append else []
    merged = current_paths + [os.path.normpath(path) for path in new_paths if path]

    unique_paths: list[str] = []
    seen: set[str] = set()
    for path in merged:
        if path in seen:
            continue
        seen.add(path)
        unique_paths.append(path)
    return ";".join(unique_paths)


def parse_extensions(raw_text: str, include_headers: bool) -> set[str]:
    raw = raw_text.strip()
    if not raw:
        extensions = set(DEFAULT_SOURCE_EXTENSIONS)
    else:
        extensions = {
            token if token.startswith(".") else f".{token}"
            for token in (part.strip() for part in raw.replace(",", " ").split())
            if token
        }

    if include_headers:
        extensions.update(HEADER_FILE_EXTENSIONS)
    return extensions


def split_existing_paths(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    directories = [path for path in paths if os.path.isdir(path)]
    files = [path for path in paths if os.path.isfile(path)]
    return directories, files


def default_extension_text() -> str:
    return DEFAULT_EXTENSION_TEXT


