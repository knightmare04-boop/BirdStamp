"""PyInstaller runtime hook: strip the Mark-of-the-Web (Zone.Identifier ADS)
from files under the frozen app so .NET Framework will load pythonnet's
Python.Runtime.dll (and any other DLL/EXE/PYD/config/json files) even when
the distribution zip was downloaded from the internet and extracted with
Windows Explorer.

This must be self-contained (stdlib only, no third-party imports, no logging
configuration) and must never raise - it runs before any other import in the
frozen app, including before app_log.setup_logging().
"""
import os
import sys

_UNBLOCK_EXTENSIONS = {".dll", ".exe", ".pyd", ".config", ".json"}


def _unblock_file(path):
    try:
        os.remove(path + ":Zone.Identifier")
    except (FileNotFoundError, PermissionError, OSError):
        pass


def _unblock_tree(root):
    if not root or not os.path.isdir(root):
        return
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            _, ext = os.path.splitext(name)
            if ext.lower() in _UNBLOCK_EXTENSIONS:
                _unblock_file(os.path.join(dirpath, name))


def _unblock_top_level(directory):
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        path = os.path.join(directory, name)
        if os.path.isfile(path) and os.path.splitext(name)[1].lower() in _UNBLOCK_EXTENSIONS:
            _unblock_file(path)


def _run():
    if sys.platform != "win32":
        return
    if not getattr(sys, "frozen", False):
        return

    try:
        meipass = getattr(sys, "_MEIPASS", None)
        exe_dir = os.path.dirname(sys.executable)

        _unblock_tree(meipass)
        # Only the exe dir's own files: _internal is covered above, and walking
        # everything would also crawl the updater's staging/backup copies.
        _unblock_top_level(exe_dir)
    except Exception:
        # Never let the runtime hook take down startup.
        pass


_run()
