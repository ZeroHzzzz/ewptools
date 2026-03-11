"""Shared constants for ewptools."""

DEFAULT_SOURCE_EXTENSIONS = {
    ".c",
    ".cpp",
    ".cxx",
    ".cc",
    ".s",
    ".asm",
    ".icf",
    ".inc",
}

HEADER_FILE_EXTENSIONS = {
    ".h",
    ".hpp",
    ".hh",
    ".hxx",
    ".inl",
    ".tpp",
}

DEFAULT_EXTENSION_TEXT = ".c .cpp .cxx .cc .s .asm .icf .inc"

IGNORED_DIRECTORIES = {"__pycache__", "node_modules"}
PROJ_DIR_PREFIX = "$PROJ_DIR$\\"
