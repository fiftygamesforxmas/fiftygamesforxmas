#!/usr/bin/env python3
"""
go.py — find, audit, and run Python programs from a filesystem tree.

Audits each .py file once (re-audits if the file changes), records third-party
packages, presents a clickable tree, and runs the selected script in a shared
virtualenv with those packages installed.
"""

from __future__ import annotations

import ast
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / cache  (not hidden)
# ---------------------------------------------------------------------------

ROOT = Path.cwd().resolve()
SELF_FILE = Path(__file__).resolve()
CACHE_PATH = ROOT / "go_audit.json"
UI_PATH = ROOT / "go_ui.json"
VENV_DIR = ROOT / "go_run_venv"
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
    "node_modules",
    "venv",
    ".venv",
    "go_run_venv",
    "go_self_venv",
    "env",
    ".env",
    "dist",
    "build",
}

IMPORT_TO_PIP = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "gi": "PyGObject",
    "wx": "wxPython",
    "tkinter": None,
    "pygame": "pygame",
    "np": "numpy",
    "pd": "pandas",
}

LOCAL_TOPLEVEL: set[str] = set()

STDLIB_FALLBACK = {
    "__future__", "_thread", "abc", "aifc", "argparse", "array", "ast",
    "asynchat", "asyncio", "asyncore", "atexit", "audioop", "base64",
    "bdb", "binascii", "binhex", "bisect", "builtins", "bz2",
    "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code",
    "codecs", "codeop", "collections", "colorsys", "compileall",
    "concurrent", "configparser", "contextlib", "contextvars", "copy",
    "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
    "distutils", "doctest", "email", "encodings", "ensurepip", "enum",
    "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
    "gettext", "glob", "graphlib", "grp", "gzip", "hashlib", "heapq",
    "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "imp",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "lib2to3", "linecache", "locale", "logging", "lzma",
    "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap",
    "modulefinder", "msilib", "msvcrt", "multiprocessing", "netrc",
    "nis", "nntplib", "ntpath", "numbers", "operator", "optparse",
    "os", "ossaudiodev", "pathlib", "pdb", "pickle", "pickletools",
    "pipes", "pkgutil", "platform", "plistlib", "poplib", "posix",
    "posixpath", "pprint", "profile", "pstats", "pty", "pwd",
    "py_compile", "pyclbr", "pydoc", "queue", "quopri", "random",
    "re", "readline", "reprlib", "resource", "rlcompleter", "runpy",
    "sched", "secrets", "select", "selectors", "shelve", "shlex",
    "shutil", "signal", "site", "smtpd", "smtplib", "sndhdr",
    "socket", "socketserver", "spwd", "sqlite3", "ssl", "stat",
    "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
    "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
    "turtledemo", "types", "typing", "unicodedata", "unittest",
    "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml",
    "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
}

DEFAULT_UI = {"x": 80, "y": 80, "w": 980, "h": 640}

# ---------------------------------------------------------------------------
# Audit cache / UI state
# ---------------------------------------------------------------------------

def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"files": {}, "packages": []}

def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")

def load_ui() -> dict:
    data = dict(DEFAULT_UI)
    if UI_PATH.exists():
        try:
            saved = json.loads(UI_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    data["w"] = max(640, int(data.get("w", DEFAULT_UI["w"])))
    data["h"] = max(400, int(data.get("h", DEFAULT_UI["h"])))
    data["x"] = int(data.get("x", DEFAULT_UI["x"]))
    data["y"] = int(data.get("y", DEFAULT_UI["y"]))
    return data

def save_ui(data: dict) -> None:
    UI_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def stdlib_names() -> set[str]:
    names = set(STDLIB_FALLBACK)
    names.update(getattr(sys, "stdlib_module_names", ()))
    names.update(sys.builtin_module_names)
    try:
        lib_dir = Path(os.__file__).resolve().parent
        if lib_dir.is_dir():
            for entry in lib_dir.iterdir():
                name = entry.name
                if name.endswith(".py"):
                    names.add(name[:-3])
                elif entry.is_dir() and not name.startswith("."):
                    names.add(name)
        dyn = lib_dir / "lib-dynload"
        if dyn.is_dir():
            for entry in dyn.iterdir():
                stem = entry.name.split(".", 1)[0]
                if stem:
                    names.add(stem)
    except OSError:
        pass
    return names

STDLIB = stdlib_names()

def extract_imports(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                found.add(node.module.split(".", 1)[0])
    return sorted(found)

def to_packages(imports: list[str]) -> list[str]:
    pkgs = []
    for name in imports:
        if name in STDLIB or name.startswith("_"):
            continue
        if name in LOCAL_TOPLEVEL:
            continue
        mapped = IMPORT_TO_PIP.get(name, name)
        if mapped and mapped not in STDLIB:
            pkgs.append(mapped)
    return sorted(set(pkgs))

def file_fingerprint(path: Path) -> dict:
    st = path.stat()
    return {"mtime": st.st_mtime, "size": st.st_size}

def needs_audit(cache: dict, path: Path) -> bool:
    key = str(path)
    prev = cache.get("files", {}).get(key)
    if not prev:
        return True
    fp = file_fingerprint(path)
    return prev.get("mtime") != fp["mtime"] or prev.get("size") != fp["size"]

def audit_file(cache: dict, path: Path) -> dict:
    imports = extract_imports(path)
    packages = to_packages(imports)
    rec = {
        **file_fingerprint(path),
        "imports": imports,
        "packages": packages,
    }
    cache.setdefault("files", {})[str(path)] = rec
    known = set(cache.get("packages", []))
    known.update(packages)
    cache["packages"] = sorted(p for p in known if p not in STDLIB)
    return rec

def scrub_stdlib_from_cache(cache: dict) -> dict:
    cache["packages"] = [p for p in cache.get("packages", []) if p not in STDLIB]
    for rec in cache.get("files", {}).values():
        rec["packages"] = [p for p in rec.get("packages", []) if p not in STDLIB]
    return cache

# ---------------------------------------------------------------------------
# Filesystem walk / tree
# ---------------------------------------------------------------------------

def discover_python_files(root: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            if name.endswith(".py"):
                found.append(Path(dirpath) / name)
    return sorted(found)

def collect_local_names(files: list[Path], root: Path) -> set[str]:
    names = set()
    for p in files:
        names.add(p.stem)
        try:
            rel = p.parent.relative_to(root)
        except ValueError:
            continue
        if rel.parts:
            names.add(rel.parts[0])
    return names

class Node:
    def __init__(self, name: str, path: Path | None = None, is_dir: bool = False):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.children: list[Node] = []
        self.expanded = True
        self.row_y = 0

def build_tree(root: Path, files: list[Path]) -> Node:
    root_node = Node(root.name or str(root), root, is_dir=True)
    index: dict[Path, Node] = {root: root_node}

    dirs = {root}
    for f in files:
        for parent in f.parents:
            if parent == root or root in parent.parents:
                dirs.add(parent)
            if parent == root:
                break

    for d in sorted(dirs, key=lambda p: len(p.parts)):
        if d == root:
            continue
        parent = index.get(d.parent)
        if parent is None:
            continue
        node = Node(d.name, d, is_dir=True)
        parent.children.append(node)
        index[d] = node

    for f in files:
        parent = index.get(f.parent)
        if parent is None:
            parent = root_node
        parent.children.append(Node(f.name, f, is_dir=False))

    def sort_node(n: Node) -> None:
        n.children.sort(key=lambda c: (not c.is_dir, c.name.lower()))
        for c in n.children:
            sort_node(c)

    sort_node(root_node)
    return root_node

def flatten(node: Node, depth: int = 0) -> list[tuple[Node, int]]:
    rows = [(node, depth)]
    if node.is_dir and node.expanded:
        for child in node.children:
            rows.extend(flatten(child, depth + 1))
    return rows

# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def copy_to_clipboard(text: str) -> tuple[bool, str]:
    if not text:
        return False, "Nothing to copy."
    system = platform.system()
    try:
        if system == "Windows":
            proc = subprocess.run(
                ["clip"],
                input=text,
                text=True,
                encoding="utf-16-le",
                check=False,
            )
            if proc.returncode != 0:
                ps = "Set-Clipboard -Value ([Console]::In.ReadToEnd())"
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    input=text,
                    text=True,
                    check=False,
                )
            if proc.returncode == 0:
                return True, "Copied failure output to clipboard."
            return False, "Windows clipboard command failed."

        if system == "Darwin":
            proc = subprocess.run(["pbcopy"], input=text, text=True, check=False)
            if proc.returncode == 0:
                return True, "Copied failure output to clipboard."
            return False, "pbcopy failed."

        for cmd in (
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            if shutil.which(cmd[0]):
                proc = subprocess.run(cmd, input=text, text=True, check=False)
                if proc.returncode == 0:
                    return True, "Copied failure output to clipboard."
        return False, "Install xclip, xsel, or wl-copy to use the clipboard."
    except OSError as exc:
        return False, f"Clipboard error: {exc}"

# ---------------------------------------------------------------------------
# Virtualenv / run
# ---------------------------------------------------------------------------

def find_system_python() -> str:
    for name in ("python3", "python"):
        path = shutil.which(name)
        if path:
            return path
    return sys.executable

def venv_python(venv: Path) -> Path:
    if platform.system() == "Windows":
        scripts = venv / "Scripts"
        for name in ("python.exe", "python3.exe"):
            candidate = scripts / name
            if candidate.exists():
                return candidate
        return scripts / "python.exe"
    bindir = venv / "bin"
    for name in ("python3", "python"):
        candidate = bindir / name
        if candidate.exists():
            return candidate
    return bindir / "python3"

def ensure_venv(venv: Path) -> Path:
    py = venv_python(venv)
    if not py.exists():
        creator = sys.executable if sys.executable else find_system_python()
        subprocess.check_call([creator, "-m", "venv", str(venv)])
    return venv_python(venv)

def install_packages(py: Path, packages: list[str], status_cb=None) -> tuple[bool, str]:
    packages = [p for p in packages if p not in STDLIB]
    if not packages:
        return True, "No third-party packages required."
    try:
        subprocess.check_call(
            [str(py), "-m", "pip", "install", "--upgrade", "pip"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if status_cb:
            status_cb("Installing: " + ", ".join(packages))
        proc = subprocess.run(
            [str(py), "-m", "pip", "install"] + packages,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout or "pip install failed")[-800:]
        return True, "Installed: " + ", ".join(packages)
    except OSError as exc:
        return False, str(exc)

def run_script(py: Path, script: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            [str(py), str(script)],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
        )
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out[-2000:]
    except OSError as exc:
        return 1, str(exc)

# ---------------------------------------------------------------------------
# Pygame GUI
# ---------------------------------------------------------------------------

def run_gui(root: Path, tree: Node, cache: dict) -> None:
    import pygame

    ui = load_ui()
    # Restore last position without pygame._sdl2 (that API segfaults on some Macs).
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{ui['x']},{ui['y']}"
    os.environ.setdefault("SDL_HINT_VIDEO_MAC_FULLSCREEN_SPACES", "0")

    pygame.init()
    pygame.display.set_caption("go.py — Python project runner")
    screen = pygame.display.set_mode((ui["w"], ui["h"]), pygame.RESIZABLE)
    clock = pygame.time.Clock()

    # Built-in default font only — SysFont can crash or hang on some Mac setups.
    font = pygame.font.Font(None, 22)
    font_small = pygame.font.Font(None, 18)
    font_title = pygame.font.Font(None, 26)

    BG = (18, 20, 26)
    PANEL = (28, 32, 42)
    ROW = (34, 38, 50)
    ROW_ALT = (30, 34, 46)
    SEL = (60, 95, 160)
    HOVER = (48, 56, 78)
    TEXT = (230, 232, 240)
    MUTED = (150, 156, 170)
    ACCENT = (120, 190, 140)
    WARN = (220, 170, 90)
    ERR = (220, 110, 110)
    LINE = (50, 56, 70)
    BTN = (70, 80, 110)
    BTN_HOVER = (90, 110, 160)
    TRACK = (24, 26, 34)
    THUMB = (90, 98, 120)
    THUMB_HOVER = (120, 130, 160)

    scroll = 0
    selected_idx = 0
    selected: Node | None = None
    status = "Double-click a .py file to install its packages and run it."
    status_color = MUTED
    last_output = ""
    last_failed = False
    last_click_time = 0.0
    last_click_node = None
    row_h = 24
    header_h = 56
    footer_h = 108
    sb_w = 16
    running = True
    busy = False
    copy_btn = pygame.Rect(0, 0, 1, 1)
    dragging_bar = False
    dragging_list = False
    drag_last_y = 0
    last_save = 0.0
    on_mac = platform.system() == "Darwin"

    def set_status(msg: str, color=MUTED) -> None:
        nonlocal status, status_color
        status = msg
        status_color = color

    def visible_rows() -> list[tuple[Node, int]]:
        return flatten(tree)

    def persist_ui(force: bool = False) -> None:
        nonlocal last_save, ui
        now = time.time()
        if not force and now - last_save < 0.5:
            return
        w, h = screen.get_size()
        ui["w"] = int(w)
        ui["h"] = int(h)
        # Position is restored via SDL_VIDEO_WINDOW_POS. Live position is not
        # queried (pygame._sdl2 segfaults on some macOS / pygame 2.6 builds).
        save_ui(ui)
        last_save = now

    def clamp_scroll(rows_n: int, view_h: int) -> None:
        nonlocal scroll
        max_scroll = max(0, rows_n * row_h - view_h)
        scroll = max(0, min(int(scroll), max_scroll))

    def ensure_index_visible(idx: int, view_h: int) -> None:
        nonlocal scroll
        top = idx * row_h
        bottom = top + row_h
        if top < scroll:
            scroll = top
        elif bottom > scroll + view_h:
            scroll = bottom - view_h

    def thumb_rect(rows_n: int, track: pygame.Rect) -> pygame.Rect:
        content = max(1, rows_n * row_h)
        view = max(1, track.h)
        if content <= view:
            return pygame.Rect(track.x, track.y, track.w, track.h)
        th = max(24, int(track.h * view / content))
        max_y = track.h - th
        max_scroll = max(1, content - view)
        ty = track.y + int(scroll * max_y / max_scroll)
        return pygame.Rect(track.x, ty, track.w, th)

    def do_copy() -> None:
        if not last_failed:
            set_status("No failure output to copy.", WARN)
            return
        ok, msg = copy_to_clipboard(last_output)
        set_status(msg, ACCENT if ok else ERR)

    def launch(node: Node) -> None:
        nonlocal last_output, last_failed, busy
        if not node.path or node.is_dir:
            return
        if node.path.resolve() == SELF_FILE:
            set_status("Refusing to launch go.py from itself.", WARN)
            return
        busy = True
        last_failed = False
        set_status(f"Preparing environment for {node.name} …", WARN)
        pygame.display.flip()

        rec = cache.get("files", {}).get(str(node.path.resolve()), {})
        packages = rec.get("packages") or to_packages(extract_imports(node.path))
        packages = [p for p in packages if p not in STDLIB]
        try:
            py = ensure_venv(VENV_DIR)
            ok, msg = install_packages(py, packages, set_status)
            if not ok:
                set_status("Install failed. Copy the message if you want.", ERR)
                last_output = msg
                last_failed = True
                busy = False
                return
            set_status(f"Running {node.name} …", ACCENT)
            pygame.event.pump()
            code, out = run_script(py, node.path)
            last_output = out.strip() or "(no output)"
            if code == 0:
                last_failed = False
                set_status(f"{node.name} finished (exit 0).", ACCENT)
            else:
                last_failed = True
                set_status(f"{node.name} exited with code {code}. Copy output available.", ERR)
        except Exception as exc:  # noqa: BLE001
            last_failed = True
            last_output = str(exc)
            set_status(f"Error: {exc}", ERR)
        busy = False

    while running:
        w, h = screen.get_size()
        tree_bottom = h - footer_h
        view_h = max(1, tree_bottom - header_h)
        rows = visible_rows()
        clamp_scroll(len(rows), view_h)
        if rows:
            selected_idx = max(0, min(selected_idx, len(rows) - 1))
            selected = rows[selected_idx][0]
        else:
            selected = None

        track = pygame.Rect(w - sb_w, header_h, sb_w, view_h)
        thumb = thumb_rect(len(rows), track)
        copy_btn = pygame.Rect(w - 210, tree_bottom + 8, 194, 26)

        mx, my = pygame.mouse.get_pos()
        hover_idx = None
        list_area = pygame.Rect(0, header_h, w - sb_w, view_h)
        if list_area.collidepoint(mx, my):
            hover_idx = (my - header_h + scroll) // row_h
            if hover_idx < 0 or hover_idx >= len(rows):
                hover_idx = None
        over_copy = copy_btn.collidepoint(mx, my) and last_failed and not busy
        over_thumb = thumb.collidepoint(mx, my)
        over_track = track.collidepoint(mx, my)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                persist_ui(force=True)
                running = False
            elif event.type == pygame.VIDEORESIZE:
                # Recreating the display on macOS pygame 2.6 often segfaults.
                # SDL already resized the window; just remember the size.
                ui["w"] = max(640, int(event.w))
                ui["h"] = max(400, int(event.h))
                if not on_mac:
                    screen = pygame.display.set_mode((ui["w"], ui["h"]), pygame.RESIZABLE)
                persist_ui(force=True)
            elif event.type == pygame.MOUSEWHEEL:
                scroll -= event.y * row_h * 3
                precise = getattr(event, "precise_y", 0) or 0
                if event.y == 0 and precise:
                    scroll -= int(precise * row_h * 3)
                clamp_scroll(len(rows), view_h)
            elif event.type == pygame.KEYDOWN:
                mods = pygame.key.get_mods()
                if event.key == pygame.K_ESCAPE:
                    persist_ui(force=True)
                    running = False
                elif event.key == pygame.K_c and (mods & pygame.KMOD_CTRL):
                    do_copy()
                elif event.key == pygame.K_DOWN:
                    if rows:
                        selected_idx = min(len(rows) - 1, selected_idx + 1)
                        ensure_index_visible(selected_idx, view_h)
                elif event.key == pygame.K_UP:
                    if rows:
                        selected_idx = max(0, selected_idx - 1)
                        ensure_index_visible(selected_idx, view_h)
                elif event.key == pygame.K_PAGEDOWN:
                    scroll += view_h - row_h
                    if rows:
                        selected_idx = min(
                            len(rows) - 1,
                            selected_idx + max(1, view_h // row_h),
                        )
                    clamp_scroll(len(rows), view_h)
                elif event.key == pygame.K_PAGEUP:
                    scroll -= view_h - row_h
                    if rows:
                        selected_idx = max(0, selected_idx - max(1, view_h // row_h))
                    clamp_scroll(len(rows), view_h)
                elif event.key == pygame.K_HOME:
                    scroll = 0
                    selected_idx = 0
                elif event.key == pygame.K_END:
                    if rows:
                        selected_idx = len(rows) - 1
                        ensure_index_visible(selected_idx, view_h)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and selected and not busy:
                    if selected.is_dir:
                        selected.expanded = not selected.expanded
                    else:
                        launch(selected)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button in (4, 5):
                    scroll += row_h * 3 if event.button == 5 else -row_h * 3
                    clamp_scroll(len(rows), view_h)
                elif event.button == 1:
                    if over_copy and not busy:
                        do_copy()
                    elif over_thumb:
                        dragging_bar = True
                        drag_last_y = my
                    elif over_track:
                        if my < thumb.y:
                            scroll -= view_h
                        else:
                            scroll += view_h
                        clamp_scroll(len(rows), view_h)
                    elif list_area.collidepoint(mx, my) and not busy:
                        if hover_idx is not None:
                            node, _depth = rows[hover_idx]
                            now = time.time()
                            is_double = (
                                last_click_node is node
                                and (now - last_click_time) < 0.45
                            )
                            last_click_time = now
                            last_click_node = node
                            selected_idx = hover_idx
                            selected = node
                            if node.is_dir:
                                node.expanded = not node.expanded
                            elif is_double:
                                launch(node)
                        dragging_list = True
                        drag_last_y = my
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                dragging_bar = False
                dragging_list = False
            elif event.type == pygame.MOUSEMOTION:
                if dragging_bar:
                    content = max(1, len(rows) * row_h)
                    max_scroll = max(1, content - view_h)
                    travel = max(1, track.h - thumb.h)
                    scroll += int((my - drag_last_y) * max_scroll / travel)
                    drag_last_y = my
                    clamp_scroll(len(rows), view_h)
                elif dragging_list:
                    scroll -= my - drag_last_y
                    drag_last_y = my
                    clamp_scroll(len(rows), view_h)

        persist_ui(False)

        screen.fill(BG)
        pygame.draw.rect(screen, PANEL, (0, 0, w, header_h))
        title = font_title.render("go.py  —  Python files under " + str(root), True, TEXT)
        screen.blit(title, (16, 10))
        pkgs = cache.get("packages") or []
        sub = font_small.render(
            f"{len(cache.get('files', {}))} audited files  |  env packages: "
            + (", ".join(pkgs) if pkgs else "(none yet)")
            + f"  |  cache: {CACHE_PATH.name}",
            True,
            MUTED,
        )
        screen.blit(sub, (16, 32))

        clip = pygame.Rect(0, header_h, w - sb_w, view_h)
        screen.set_clip(clip)
        for i, (node, depth) in enumerate(rows):
            y = header_h + i * row_h - scroll
            if y + row_h < header_h or y > tree_bottom:
                continue
            rect = pygame.Rect(0, y, w - sb_w, row_h)
            if i == selected_idx:
                color = SEL
            elif hover_idx == i:
                color = HOVER
            else:
                color = ROW if i % 2 == 0 else ROW_ALT
            pygame.draw.rect(screen, color, rect)

            if node.is_dir:
                prefix = "[-] " if node.expanded else "[+] "
            else:
                prefix = "    "
            rec = cache.get("files", {}).get(str(node.path.resolve()) if node.path else "", {})
            extra = ""
            if not node.is_dir:
                pkgs_here = rec.get("packages") or []
                extra = "   (" + ", ".join(pkgs_here) + ")" if pkgs_here else "   (stdlib only)"
            label = prefix + ("  " * depth) + node.name + extra
            col = ACCENT if not node.is_dir else TEXT
            if node.path and node.path.resolve() == SELF_FILE:
                col = MUTED
                label += "  [this utility]"
            surf = font.render(label, True, col)
            screen.blit(surf, (12, y + 3))
        screen.set_clip(None)

        pygame.draw.rect(screen, TRACK, track)
        pygame.draw.rect(screen, THUMB_HOVER if over_thumb or dragging_bar else THUMB, thumb)

        pygame.draw.rect(screen, PANEL, (0, tree_bottom, w, footer_h))
        pygame.draw.line(screen, LINE, (0, tree_bottom), (w, tree_bottom))
        status_surf = font.render(status[: max(0, (w - 230) // 8)], True, status_color)
        screen.blit(status_surf, (16, tree_bottom + 10))

        if last_failed:
            btn_color = BTN_HOVER if over_copy else BTN
            pygame.draw.rect(screen, btn_color, copy_btn)
            btn_label = font_small.render("Copy failure output", True, TEXT)
            screen.blit(btn_label, (copy_btn.x + 18, copy_btn.y + 5))

        oy = tree_bottom + 40
        for line in last_output.splitlines()[:3]:
            screen.blit(font_small.render(line[:140], True, MUTED), (16, oy))
            oy += 16

        hint = font_small.render(
            "Arrows / PgUp / PgDn / mouse wheel / drag list or scrollbar  |  "
            "Double-click to run  |  Ctrl+C copy failure  |  Esc quit",
            True,
            MUTED,
        )
        screen.blit(hint, (16, h - 20))

        pygame.display.flip()
        clock.tick(60)

    persist_ui(force=True)
    pygame.quit()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"Scanning {ROOT} …")
    print(f"Audit cache: {CACHE_PATH}")
    print(f"Window state: {UI_PATH}")
    files = discover_python_files(ROOT)
    global LOCAL_TOPLEVEL
    LOCAL_TOPLEVEL = collect_local_names(files, ROOT)

    cache = scrub_stdlib_from_cache(load_cache())
    save_cache(cache)

    audited = 0
    skipped = 0
    for path in files:
        key_path = path.resolve()
        if key_path == SELF_FILE:
            if needs_audit(cache, key_path):
                cache.setdefault("files", {})[str(key_path)] = {
                    **file_fingerprint(key_path),
                    "imports": ["pygame"],
                    "packages": [],
                }
                audited += 1
            else:
                skipped += 1
            continue
        if needs_audit(cache, key_path):
            rec = audit_file(cache, key_path)
            audited += 1
            print(f"  audited {path.relative_to(ROOT)} -> {rec['packages'] or 'stdlib only'}")
        else:
            skipped += 1
    save_cache(cache)
    print(f"Done. audited={audited} cached={skipped} unique_packages={cache.get('packages')}")

    tree = build_tree(ROOT, [p.resolve() for p in files])
    try:
        run_gui(ROOT, tree, cache)
    except ImportError:
        print("pygame is not installed. Use go.sh / go.bat to bootstrap the GUI environment.")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())