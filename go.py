#!/usr/bin/env python3
"""
go.py — find, audit, and run Python programs from a filesystem tree.
"""

from __future__ import annotations

import ast
import io
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd().resolve()
SELF_FILE = Path(__file__).resolve()
SELF_DIR = SELF_FILE.parent
CACHE_PATH = ROOT / "go_audit.json"
UI_PATH = ROOT / "go_ui.json"
LAUNCH_PATH = ROOT / "go_launches.json"
VENV_DIR = ROOT / "go_run_venv"
IGNORE_NAME = "ignore.txt"
SPLASH_SECONDS = 10.0

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".nox", ".idea", ".vscode", "node_modules",
    "venv", ".venv", "go_run_venv", "go_self_venv", "env", ".env",
    "dist", "build",
}

IMPORT_TO_PIP = {
    "PIL": "Pillow", "cv2": "opencv-python", "sklearn": "scikit-learn",
    "skimage": "scikit-image", "yaml": "PyYAML", "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil", "dotenv": "python-dotenv",
    "gi": "PyGObject", "wx": "wxPython", "tkinter": None, "pygame": "pygame",
    "np": "numpy", "pd": "pandas",
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

DEFAULT_UI = {"x": 80, "y": 80, "w": 980, "h": 640, "view": "icons", "sort": "name"}
IMAGE_CACHE: dict[str, object] = {}

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default

def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

def load_cache() -> dict:
    return load_json(CACHE_PATH, {"files": {}, "packages": []})

def save_cache(cache: dict) -> None:
    save_json(CACHE_PATH, cache)

def load_ui() -> dict:
    data = dict(DEFAULT_UI)
    saved = load_json(UI_PATH, {})
    if isinstance(saved, dict):
        data.update(saved)
    data["w"] = max(640, int(data.get("w", DEFAULT_UI["w"])))
    data["h"] = max(400, int(data.get("h", DEFAULT_UI["h"])))
    data["x"] = int(data.get("x", DEFAULT_UI["x"]))
    data["y"] = int(data.get("y", DEFAULT_UI["y"]))
    if data.get("view") not in ("icons", "tree"):
        data["view"] = "icons"
    if data.get("sort") not in ("name", "launches"):
        data["sort"] = "name"
    return data

def save_ui(data: dict) -> None:
    save_json(UI_PATH, data)

def load_launches() -> dict:
    raw = load_json(LAUNCH_PATH, {})
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                out[k] = 0
    return out

def save_launches(data: dict) -> None:
    save_json(LAUNCH_PATH, data)

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

def read_ignore_file(directory: Path) -> list[str]:
    path = directory / IGNORE_NAME
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rules = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.replace("\\", "/").strip("/")
        if line:
            rules.append(line)
    return rules

def collect_ignore_rules(root: Path) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for pattern in read_ignore_file(root):
        found.append((root, pattern))
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        base = Path(dirpath)
        if base.resolve() == root.resolve():
            continue
        if IGNORE_NAME in filenames:
            for pattern in read_ignore_file(base):
                found.append((base, pattern))
    return found

def posix_rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.name

def rule_matches(path: Path, base: Path, pattern: str) -> bool:
    rel = posix_rel(path, base)
    pat = pattern.strip("/")
    if not pat:
        return False
    if rel == pat or rel.startswith(pat + "/"):
        return True
    if "/" not in pat and path.name == pat:
        return True
    return False

def is_path_ignored(path: Path, root: Path, rules: list[tuple[Path, str]]) -> bool:
    for base, pattern in rules:
        if rule_matches(path, base, pattern) or rule_matches(path, root, pattern):
            return True
    return False

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
        if name in STDLIB or name.startswith("_") or name in LOCAL_TOPLEVEL:
            continue
        mapped = IMPORT_TO_PIP.get(name, name)
        if mapped and mapped not in STDLIB:
            pkgs.append(mapped)
    return sorted(set(pkgs))

def file_fingerprint(path: Path) -> dict:
    st = path.stat()
    return {"mtime": st.st_mtime, "size": st.st_size}

def needs_audit(cache: dict, path: Path) -> bool:
    prev = cache.get("files", {}).get(str(path))
    if not prev:
        return True
    fp = file_fingerprint(path)
    return prev.get("mtime") != fp["mtime"] or prev.get("size") != fp["size"]

def audit_file(cache: dict, path: Path) -> dict:
    imports = extract_imports(path)
    packages = to_packages(imports)
    rec = {**file_fingerprint(path), "imports": imports, "packages": packages}
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

def prune_ignored_from_cache(cache: dict, kept: list[Path]) -> dict:
    keep = {str(p.resolve()) for p in kept}
    files = cache.get("files", {})
    cache["files"] = {k: v for k, v in files.items() if k in keep}
    pkgs: set[str] = set()
    for rec in cache["files"].values():
        pkgs.update(rec.get("packages") or [])
    cache["packages"] = sorted(p for p in pkgs if p not in STDLIB)
    return cache

def discover_python_files(root: Path) -> list[Path]:
    rules = collect_ignore_rules(root)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        directory = Path(dirpath)
        if is_path_ignored(directory, root, rules):
            dirnames[:] = []
            continue
        keep = []
        for d in dirnames:
            if d in SKIP_DIRS or d.startswith("."):
                continue
            child = directory / d
            if not is_path_ignored(child, root, rules):
                keep.append(d)
        dirnames[:] = keep
        local = read_ignore_file(directory)
        for name in filenames:
            if name == IGNORE_NAME:
                continue
            child = directory / name
            if any(rule_matches(child, directory, pat) for pat in local):
                continue
            if is_path_ignored(child, root, rules):
                continue
            if name.endswith(".py"):
                found.append(child)
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
        (index.get(f.parent) or root_node).children.append(Node(f.name, f, is_dir=False))

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

def copy_to_clipboard(text: str) -> tuple[bool, str]:
    if not text:
        return False, "Nothing to copy."
    system = platform.system()
    try:
        if system == "Windows":
            proc = subprocess.run(["clip"], input=text, text=True, encoding="utf-16-le", check=False)
            if proc.returncode != 0:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                    input=text, text=True, check=False,
                )
            ok = proc.returncode == 0
            return ok, "Copied failure output to clipboard." if ok else "Windows clipboard command failed."
        if system == "Darwin":
            proc = subprocess.run(["pbcopy"], input=text, text=True, check=False)
            ok = proc.returncode == 0
            return ok, "Copied failure output to clipboard." if ok else "pbcopy failed."
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
            if shutil.which(cmd[0]):
                proc = subprocess.run(cmd, input=text, text=True, check=False)
                if proc.returncode == 0:
                    return True, "Copied failure output to clipboard."
        return False, "Install xclip, xsel, or wl-copy to use the clipboard."
    except OSError as exc:
        return False, f"Clipboard error: {exc}"

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
            if (scripts / name).exists():
                return scripts / name
        return scripts / "python.exe"
    bindir = venv / "bin"
    for name in ("python3", "python"):
        if (bindir / name).exists():
            return bindir / name
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
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if status_cb:
            status_cb("Installing: " + ", ".join(packages))
        proc = subprocess.run([str(py), "-m", "pip", "install"] + packages, capture_output=True, text=True)
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout or "pip install failed")[-800:]
        return True, "Installed: " + ", ".join(packages)
    except OSError as exc:
        return False, str(exc)

def run_script(py: Path, script: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run([str(py), str(script)], cwd=str(script.parent), capture_output=True, text=True)
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out[-2000:]
    except OSError as exc:
        return 1, str(exc)

def first_existing(*paths: Path) -> Path | None:
    for p in paths:
        if p.is_file():
            return p
    return None

def program_icon_path(script: Path) -> Path | None:
    return first_existing(
        script.with_suffix(".ico"),
        script.with_suffix(".png"),
        script.with_suffix(".jpg"),
    )

def default_icon_path() -> Path | None:
    # Launch directory first, then the folder that contains go.py.
    return first_existing(
        ROOT / "default.ico",
        ROOT / "default.png",
        ROOT / "default.jpg",
        SELF_DIR / "default.ico",
        SELF_DIR / "default.png",
        SELF_DIR / "default.jpg",
    )

def program_photo_path(script: Path) -> Path | None:
    return first_existing(script.with_suffix(".jpg"), script.with_suffix(".jpeg"))

def default_photo_path() -> Path | None:
    return first_existing(
        ROOT / "default.jpg",
        ROOT / "default.jpeg",
        SELF_DIR / "default.jpg",
        SELF_DIR / "default.jpeg",
        ROOT / "default.png",
        SELF_DIR / "default.png",
    )

def surface_from_bytes(pygame_mod, data: bytes):
    try:
        return pygame_mod.image.load(io.BytesIO(data)).convert_alpha()
    except Exception:
        return None

def load_ico_best(pygame_mod, path: Path):
    """Parse a Windows ICO and load the largest embedded PNG or BMP."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 6:
        return None
    reserved, itype, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or itype not in (1, 2) or count < 1:
        return None
    entries = []
    off = 6
    for _ in range(count):
        if off + 16 > len(data):
            break
        w, h, _colors, _res, _planes, _bpp, nbytes, img_off = struct.unpack_from("<BBBBHHII", data, off)
        width = 256 if w == 0 else w
        height = 256 if h == 0 else h
        entries.append((width * height, img_off, nbytes))
        off += 16
    entries.sort(reverse=True)
    for _area, img_off, nbytes in entries:
        chunk = data[img_off:img_off + nbytes]
        if chunk.startswith(b"\x89PNG"):
            surf = surface_from_bytes(pygame_mod, chunk)
            if surf is not None:
                return surf
        # BMP stored without BITMAPFILEHEADER; prefix one.
        if len(chunk) >= 40:
            bmp = b"BM" + struct.pack("<IHHI", 14 + len(chunk), 0, 0, 14 + 40) + chunk
            surf = surface_from_bytes(pygame_mod, bmp)
            if surf is not None:
                return surf
    return surface_from_bytes(pygame_mod, data)

def load_image_file(pygame_mod, path: Path):
    if path.suffix.lower() == ".ico":
        surf = load_ico_best(pygame_mod, path)
        if surf is not None:
            return surf
    try:
        return pygame_mod.image.load(str(path)).convert_alpha()
    except Exception:
        try:
            return pygame_mod.image.load(str(path)).convert()
        except Exception:
            return None

def load_surface(path: Path | None, pygame_mod, size=None):
    key = f"{path}:{size}" if path else f"missing:{size}"
    if key in IMAGE_CACHE:
        return IMAGE_CACHE[key]
    surf = None
    if path is not None:
        loaded = load_image_file(pygame_mod, path)
        if loaded is not None and size:
            surf = pygame_mod.transform.smoothscale(loaded, size)
        else:
            surf = loaded
    IMAGE_CACHE[key] = surf
    return surf

def make_default_icon(pygame_mod, size=(64, 64)):
    key = f"gen-icon:{size}"
    if key in IMAGE_CACHE:
        return IMAGE_CACHE[key]
    surf = pygame_mod.Surface(size, pygame_mod.SRCALPHA)
    surf.fill((40, 90, 140, 255))
    pygame_mod.draw.rect(surf, (80, 170, 220), surf.get_rect(), 3)
    font = pygame_mod.font.Font(None, max(16, size[1] // 2))
    label = font.render("PY", True, (240, 240, 240))
    surf.blit(label, label.get_rect(center=surf.get_rect().center))
    IMAGE_CACHE[key] = surf
    return surf

def make_default_photo(pygame_mod, size, title: str):
    surf = pygame_mod.Surface(size)
    surf.fill((16, 18, 24))
    pygame_mod.draw.rect(surf, (70, 80, 110), surf.get_rect(), 4)
    font = pygame_mod.font.Font(None, 36)
    small = pygame_mod.font.Font(None, 22)
    t = font.render(title, True, (230, 232, 240))
    s = small.render("No preview JPEG found — using default picture", True, (160, 166, 180))
    surf.blit(t, t.get_rect(center=(size[0] // 2, size[1] // 2 - 16)))
    surf.blit(s, s.get_rect(center=(size[0] // 2, size[1] // 2 + 20)))
    return surf

def icon_for(script: Path, pygame_mod, size=(64, 64)):
    surf = load_surface(program_icon_path(script), pygame_mod, size)
    if surf is None:
        surf = load_surface(default_icon_path(), pygame_mod, size)
    if surf is None:
        surf = make_default_icon(pygame_mod, size)
    return surf

def photo_for(script: Path, pygame_mod, size):
    surf = load_surface(program_photo_path(script), pygame_mod, size)
    if surf is None:
        surf = load_surface(default_photo_path(), pygame_mod, size)
    if surf is None:
        surf = make_default_photo(pygame_mod, size, script.stem)
    return surf

def run_gui(root: Path, tree: Node, files: list[Path], cache: dict, launches: dict) -> None:
    import pygame

    ui = load_ui()
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{ui['x']},{ui['y']}"
    os.environ.setdefault("SDL_HINT_VIDEO_MAC_FULLSCREEN_SPACES", "0")

    pygame.init()
    pygame.display.set_caption("go.py — Python project runner")
    screen = pygame.display.set_mode((ui["w"], ui["h"]), pygame.RESIZABLE)
    clock = pygame.time.Clock()
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
    DIM = (0, 0, 0, 160)
    MODAL = (28, 32, 42)

    view = ui.get("view", "icons")
    sort_mode = ui.get("sort", "name")
    scroll = 0
    selected_idx = 0
    status = "Icon view. Double-click a program to launch it."
    status_color = MUTED
    last_output = ""
    last_failed = False
    last_click_time = 0.0
    last_click_key = None
    row_h = 24
    header_h = 86
    footer_h = 108
    sb_w = 16
    cell_w, cell_h, icon_s = 120, 128, 64
    running = True
    busy = False
    dragging_bar = False
    dragging_list = False
    drag_last_y = 0
    last_save = 0.0
    on_mac = platform.system() == "Darwin"
    modal_open = False
    modal_script: Path | None = None
    modal_started = 0.0
    modal_photo = None
    launch_started = False

    def set_status(msg: str, color=MUTED) -> None:
        nonlocal status, status_color
        status = msg
        status_color = color

    def persist_ui(force: bool = False) -> None:
        nonlocal last_save, ui
        now = time.time()
        if not force and now - last_save < 0.5:
            return
        w, h = screen.get_size()
        ui["w"], ui["h"] = int(w), int(h)
        ui["view"], ui["sort"] = view, sort_mode
        save_ui(ui)
        last_save = now

    def sorted_files() -> list[Path]:
        py_files = [p for p in files if p.resolve() != SELF_FILE]
        if sort_mode == "launches":
            return sorted(py_files, key=lambda p: (-launches.get(str(p.resolve()), 0), p.stem.lower()))
        return sorted(py_files, key=lambda p: p.stem.lower())

    def clamp_scroll(content_h: int, view_h: int) -> None:
        nonlocal scroll
        scroll = max(0, min(int(scroll), max(0, content_h - view_h)))

    def thumb_rect(content_h: int, track: pygame.Rect) -> pygame.Rect:
        viewh = max(1, track.h)
        content = max(1, content_h)
        if content <= viewh:
            return pygame.Rect(track.x, track.y, track.w, track.h)
        th = max(24, int(track.h * viewh / content))
        max_scroll = max(1, content - viewh)
        ty = track.y + int(scroll * (track.h - th) / max_scroll)
        return pygame.Rect(track.x, ty, track.w, th)

    def button(rect, label, active=False, hover=False):
        color = SEL if active else (BTN_HOVER if hover else BTN)
        pygame.draw.rect(screen, color, rect)
        txt = font_small.render(label, True, TEXT)
        screen.blit(txt, txt.get_rect(center=rect.center))

    def do_copy() -> None:
        if not last_failed:
            set_status("No failure output to copy.", WARN)
            return
        ok, msg = copy_to_clipboard(last_output)
        set_status(msg, ACCENT if ok else ERR)

    def modal_rect():
        w, h = screen.get_size()
        mw, mh = min(720, w - 40), min(520, h - 40)
        return pygame.Rect((w - mw) // 2, (h - mh) // 2, mw, mh)

    def draw_modal():
        w, h = screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill(DIM)
        screen.blit(shade, (0, 0))
        box = modal_rect()
        pygame.draw.rect(screen, MODAL, box)
        pygame.draw.rect(screen, LINE, box, 2)
        title = font_title.render("Launching " + (modal_script.stem if modal_script else ""), True, TEXT)
        screen.blit(title, (box.x + 16, box.y + 12))
        inner = pygame.Rect(box.x + 16, box.y + 48, box.w - 32, box.h - 88)
        pygame.draw.rect(screen, (12, 14, 18), inner)
        if modal_photo is not None:
            fitted = pygame.transform.smoothscale(
                modal_photo,
                (
                    inner.w,
                    int(modal_photo.get_height() * inner.w / max(1, modal_photo.get_width())),
                ),
            )
            if fitted.get_height() > inner.h:
                fitted = pygame.transform.smoothscale(
                    modal_photo,
                    (
                        int(modal_photo.get_width() * inner.h / max(1, modal_photo.get_height())),
                        inner.h,
                    ),
                )
            screen.blit(fitted, fitted.get_rect(center=inner.center))
        left = max(0.0, SPLASH_SECONDS - (time.time() - modal_started))
        note = "Program starting…" if launch_started else f"Preview  {left:.0f}s  (closes when the program starts)"
        screen.blit(font_small.render(note, True, MUTED), (box.x + 16, box.bottom - 28))

    def pump_modal_frame() -> bool:
        """Draw modal and eat events. Return False if the app should quit."""
        nonlocal running
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                return False
            if event.type == pygame.VIDEORESIZE:
                ui["w"] = max(640, int(event.w))
                ui["h"] = max(400, int(event.h))
                if not on_mac:
                    pygame.display.set_mode((ui["w"], ui["h"]), pygame.RESIZABLE)
        w, h = screen.get_size()
        screen.fill(BG)
        pygame.draw.rect(screen, PANEL, (0, 0, w, header_h))
        screen.blit(font_title.render("go.py  —  " + str(root), True, TEXT), (16, 10))
        draw_modal()
        pygame.display.flip()
        clock.tick(30)
        return running

    def close_modal_if_needed(force: bool = False) -> None:
        nonlocal modal_open, modal_photo
        if not modal_open:
            return
        expired = time.time() - modal_started >= SPLASH_SECONDS
        if force or launch_started or expired:
            modal_open = False
            modal_photo = None

    def launch(script: Path) -> None:
        nonlocal last_output, last_failed, busy, modal_open, modal_script
        nonlocal modal_started, modal_photo, launch_started
        if script.resolve() == SELF_FILE:
            set_status("Refusing to launch go.py from itself.", WARN)
            return
        busy = True
        last_failed = False
        launch_started = False
        modal_script = script
        modal_started = time.time()
        modal_open = True
        pic_path = program_photo_path(script) or default_photo_path()
        raw = load_surface(pic_path, pygame, None) if pic_path else None
        modal_photo = raw if raw is not None else make_default_photo(pygame, (640, 400), script.stem)
        pump_modal_frame()

        rec = cache.get("files", {}).get(str(script.resolve()), {})
        packages = [p for p in (rec.get("packages") or to_packages(extract_imports(script))) if p not in STDLIB]
        try:
            set_status(f"Preparing environment for {script.name} …", WARN)
            pump_modal_frame()
            py = ensure_venv(VENV_DIR)
            close_modal_if_needed()
            pump_modal_frame()
            ok, msg = install_packages(py, packages, set_status)
            close_modal_if_needed()
            pump_modal_frame()
            if not ok:
                set_status("Install failed. Copy the message if you want.", ERR)
                last_output = msg
                last_failed = True
                modal_open = False
                busy = False
                return
            key = str(script.resolve())
            launches[key] = launches.get(key, 0) + 1
            save_launches(launches)
            set_status(f"Running {script.name} …", ACCENT)
            launch_started = True
            close_modal_if_needed(force=True)
            pygame.event.pump()
            code, out = run_script(py, script)
            last_output = out.strip() or "(no output)"
            if code == 0:
                last_failed = False
                set_status(f"{script.name} finished (exit 0).", ACCENT)
            else:
                last_failed = True
                set_status(f"{script.name} exited with code {code}. Copy output available.", ERR)
        except Exception as exc:  # noqa: BLE001
            last_failed = True
            last_output = str(exc)
            set_status(f"Error: {exc}", ERR)
            modal_open = False
        busy = False
        launch_started = False

    while running:
        w, h = screen.get_size()
        tree_bottom = h - footer_h
        view_h = max(1, tree_bottom - header_h)
        py_files = sorted_files()
        cols = max(1, (w - sb_w - 16) // cell_w)
        icon_rows = (len(py_files) + cols - 1) // cols if py_files else 0
        tree_rows = flatten(tree)
        content_h = icon_rows * cell_h if view == "icons" else len(tree_rows) * row_h
        clamp_scroll(content_h, view_h)

        track = pygame.Rect(w - sb_w, header_h, sb_w, view_h)
        thumb = thumb_rect(content_h, track)
        copy_btn = pygame.Rect(w - 210, tree_bottom + 8, 194, 26)
        btn_icons = pygame.Rect(16, 48, 90, 26)
        btn_tree = pygame.Rect(112, 48, 90, 26)
        btn_sort = pygame.Rect(218, 48, 170, 26)

        mx, my = pygame.mouse.get_pos()
        hover_idx = None
        list_area = pygame.Rect(0, header_h, w - sb_w, view_h)
        icon_hit = None
        if not modal_open and view == "icons" and list_area.collidepoint(mx, my):
            col = (mx - 12) // cell_w
            row = (my - header_h + scroll) // cell_h
            if 0 <= col < cols:
                idx = int(row) * cols + int(col)
                if 0 <= idx < len(py_files):
                    icon_hit = idx
                    hover_idx = idx
        elif not modal_open and view == "tree" and list_area.collidepoint(mx, my):
            hover_idx = (my - header_h + scroll) // row_h
            if hover_idx < 0 or hover_idx >= len(tree_rows):
                hover_idx = None

        over_copy = copy_btn.collidepoint(mx, my) and last_failed and not busy and not modal_open
        over_thumb = thumb.collidepoint(mx, my) and not modal_open
        over_track = track.collidepoint(mx, my) and not modal_open

        if modal_open:
            close_modal_if_needed()
            if not pump_modal_frame():
                break
            persist_ui(False)
            continue

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                persist_ui(True)
                running = False
            elif event.type == pygame.VIDEORESIZE:
                ui["w"] = max(640, int(event.w))
                ui["h"] = max(400, int(event.h))
                if not on_mac:
                    screen = pygame.display.set_mode((ui["w"], ui["h"]), pygame.RESIZABLE)
                persist_ui(True)
            elif event.type == pygame.MOUSEWHEEL:
                scroll -= event.y * (cell_h if view == "icons" else row_h)
                clamp_scroll(content_h, view_h)
            elif event.type == pygame.KEYDOWN:
                mods = pygame.key.get_mods()
                if event.key == pygame.K_ESCAPE:
                    persist_ui(True)
                    running = False
                elif event.key == pygame.K_c and (mods & pygame.KMOD_CTRL):
                    do_copy()
                elif event.key == pygame.K_TAB:
                    view = "tree" if view == "icons" else "icons"
                    scroll = 0
                elif event.key == pygame.K_DOWN:
                    limit = (len(py_files) if view == "icons" else len(tree_rows)) - 1
                    selected_idx = min(max(0, limit), selected_idx + (cols if view == "icons" else 1))
                elif event.key == pygame.K_UP:
                    selected_idx = max(0, selected_idx - (cols if view == "icons" else 1))
                elif event.key == pygame.K_RIGHT and view == "icons":
                    selected_idx = min(max(0, len(py_files) - 1), selected_idx + 1)
                elif event.key == pygame.K_LEFT and view == "icons":
                    selected_idx = max(0, selected_idx - 1)
                elif event.key == pygame.K_PAGEDOWN:
                    scroll += view_h - 24
                elif event.key == pygame.K_PAGEUP:
                    scroll -= view_h - 24
                elif event.key == pygame.K_HOME:
                    scroll = 0
                    selected_idx = 0
                elif event.key == pygame.K_END:
                    scroll = 10 ** 9
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and not busy:
                    if view == "icons" and py_files:
                        selected_idx = max(0, min(selected_idx, len(py_files) - 1))
                        launch(py_files[selected_idx])
                    elif view == "tree" and tree_rows:
                        selected_idx = max(0, min(selected_idx, len(tree_rows) - 1))
                        node, _ = tree_rows[selected_idx]
                        if node.is_dir:
                            node.expanded = not node.expanded
                        elif node.path:
                            launch(node.path)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button in (4, 5):
                    scroll += (cell_h if view == "icons" else row_h) * (1 if event.button == 5 else -1)
                elif event.button == 1:
                    if btn_icons.collidepoint(mx, my):
                        view = "icons"
                        scroll = 0
                    elif btn_tree.collidepoint(mx, my):
                        view = "tree"
                        scroll = 0
                    elif btn_sort.collidepoint(mx, my):
                        sort_mode = "launches" if sort_mode == "name" else "name"
                        scroll = 0
                    elif over_copy and not busy:
                        do_copy()
                    elif over_thumb:
                        dragging_bar = True
                        drag_last_y = my
                    elif over_track:
                        scroll += -view_h if my < thumb.y else view_h
                    elif list_area.collidepoint(mx, my) and not busy:
                        now = time.time()
                        if view == "icons" and icon_hit is not None:
                            key = str(py_files[icon_hit])
                            is_double = last_click_key == key and now - last_click_time < 0.45
                            last_click_time, last_click_key = now, key
                            selected_idx = icon_hit
                            if is_double:
                                launch(py_files[icon_hit])
                        elif view == "tree" and hover_idx is not None:
                            node, _ = tree_rows[hover_idx]
                            key = str(node.path)
                            is_double = last_click_key == key and now - last_click_time < 0.45
                            last_click_time, last_click_key = now, key
                            selected_idx = hover_idx
                            if node.is_dir:
                                node.expanded = not node.expanded
                            elif node.path and is_double:
                                launch(node.path)
                        dragging_list = True
                        drag_last_y = my
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                dragging_bar = dragging_list = False
            elif event.type == pygame.MOUSEMOTION:
                if dragging_bar:
                    travel = max(1, track.h - thumb.h)
                    max_scroll = max(1, content_h - view_h)
                    scroll += int((my - drag_last_y) * max_scroll / travel)
                    drag_last_y = my
                elif dragging_list:
                    scroll -= my - drag_last_y
                    drag_last_y = my

        persist_ui(False)
        screen.fill(BG)
        pygame.draw.rect(screen, PANEL, (0, 0, w, header_h))
        screen.blit(font_title.render("go.py  —  " + str(root), True, TEXT), (16, 10))
        button(btn_icons, "Icons", active=view == "icons", hover=btn_icons.collidepoint(mx, my))
        button(btn_tree, "Tree", active=view == "tree", hover=btn_tree.collidepoint(mx, my))
        button(btn_sort, "Sort: " + ("Launches" if sort_mode == "launches" else "Name"), hover=btn_sort.collidepoint(mx, my))

        clip = pygame.Rect(0, header_h, w - sb_w, view_h)
        screen.set_clip(clip)
        if view == "icons":
            for i, path in enumerate(py_files):
                r, c = divmod(i, cols)
                x = 12 + c * cell_w
                y = header_h + r * cell_h - scroll
                if y + cell_h < header_h or y > tree_bottom:
                    continue
                box = pygame.Rect(x, y, cell_w - 8, cell_h - 8)
                if i == selected_idx:
                    pygame.draw.rect(screen, SEL, box)
                elif i == hover_idx:
                    pygame.draw.rect(screen, HOVER, box)
                ico = icon_for(path, pygame, (icon_s, icon_s))
                screen.blit(ico, ico.get_rect(midtop=(box.centerx, box.y + 8)))
                label = font_small.render(path.stem[:16], True, TEXT)
                screen.blit(label, label.get_rect(midtop=(box.centerx, box.y + 8 + icon_s + 6)))
                count = launches.get(str(path.resolve()), 0)
                if count:
                    nlab = font_small.render(str(count), True, MUTED)
                    screen.blit(nlab, (box.right - 18, box.y + 4))
        else:
            for i, (node, depth) in enumerate(tree_rows):
                y = header_h + i * row_h - scroll
                if y + row_h < header_h or y > tree_bottom:
                    continue
                rect = pygame.Rect(0, y, w - sb_w, row_h)
                color = SEL if i == selected_idx else HOVER if hover_idx == i else (ROW if i % 2 == 0 else ROW_ALT)
                pygame.draw.rect(screen, color, rect)
                prefix = ("[-] " if node.expanded else "[+] ") if node.is_dir else "    "
                extra = ""
                if node.path and not node.is_dir:
                    pkgs_here = cache.get("files", {}).get(str(node.path.resolve()), {}).get("packages") or []
                    extra = "   (" + ", ".join(pkgs_here) + ")" if pkgs_here else "   (stdlib only)"
                label = prefix + ("  " * depth) + node.name + extra
                col = MUTED if node.path and node.path.resolve() == SELF_FILE else (ACCENT if not node.is_dir else TEXT)
                screen.blit(font.render(label, True, col), (12, y + 3))
        screen.set_clip(None)

        pygame.draw.rect(screen, TRACK, track)
        pygame.draw.rect(screen, THUMB_HOVER if over_thumb or dragging_bar else THUMB, thumb)
        pygame.draw.rect(screen, PANEL, (0, tree_bottom, w, footer_h))
        pygame.draw.line(screen, LINE, (0, tree_bottom), (w, tree_bottom))
        screen.blit(font.render(status[: max(0, (w - 230) // 8)], True, status_color), (16, tree_bottom + 10))
        if last_failed:
            pygame.draw.rect(screen, BTN_HOVER if over_copy else BTN, copy_btn)
            screen.blit(font_small.render("Copy failure output", True, TEXT), (copy_btn.x + 18, copy_btn.y + 5))
        oy = tree_bottom + 40
        for line in last_output.splitlines()[:3]:
            screen.blit(font_small.render(line[:140], True, MUTED), (16, oy))
            oy += 16
        screen.blit(font_small.render(
            "Icons / Tree / Sort  |  Wheel or arrows to scroll  |  Double-click to run",
            True, MUTED), (16, h - 20))

        pygame.display.flip()
        clock.tick(60)

    persist_ui(True)
    pygame.quit()

def force_audit_from_args(argv: list[str]) -> bool:
    return any(a == "-audit" for a in argv[1:])

def main() -> int:
    if force_audit_from_args(sys.argv):
        if CACHE_PATH.exists():
            CACHE_PATH.unlink()
            print(f"Deleted audit cache {CACHE_PATH}")
        print("Forcing a full re-audit of all visible Python files.")

    print(f"Scanning {ROOT} …")
    print(f"Audit cache: {CACHE_PATH}")
    icon = default_icon_path()
    print(f"Default icon: {icon if icon else '(none found — using drawn fallback)'}")
    files = discover_python_files(ROOT)
    global LOCAL_TOPLEVEL
    LOCAL_TOPLEVEL = collect_local_names(files, ROOT)
    cache = prune_ignored_from_cache(scrub_stdlib_from_cache(load_cache()), [p.resolve() for p in files])
    launches = load_launches()

    audited = skipped = 0
    for path in files:
        key_path = path.resolve()
        if key_path == SELF_FILE:
            if needs_audit(cache, key_path):
                cache.setdefault("files", {})[str(key_path)] = {
                    **file_fingerprint(key_path), "imports": ["pygame"], "packages": []
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
        run_gui(ROOT, tree, [p.resolve() for p in files], cache, launches)
    except ImportError:
        print("pygame is not installed. Use go.sh / go.bat to bootstrap the GUI environment.")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())