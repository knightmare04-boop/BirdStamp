"""Logging setup shared by desktop.py and the backend.

Owned by the PACKAGING agent. Backend modules should never configure logging
themselves - they just do `logging.getLogger(__name__)` and rely on the root
logger configured here.
"""
import io
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_configured = False
_log_path = None


def get_app_data_dir() -> str:
    """Return (and create) a writable per-user app data directory.

    Prefers %LOCALAPPDATA%\\BirdStamp, falling back to ~/.birdstamp if
    LOCALAPPDATA isn't set (e.g. non-Windows dev environments).
    """
    base = os.environ.get("LOCALAPPDATA")
    if base:
        app_dir = os.path.join(base, "BirdStamp")
    else:
        app_dir = os.path.join(os.path.expanduser("~"), ".birdstamp")

    try:
        os.makedirs(app_dir, exist_ok=True)
    except Exception:
        # Last resort: fall back to home directory if LOCALAPPDATA is not writable.
        app_dir = os.path.join(os.path.expanduser("~"), ".birdstamp")
        os.makedirs(app_dir, exist_ok=True)

    return app_dir


def setup_logging() -> str:
    """Configure the root logger. Idempotent - safe to call multiple times.

    Returns the path to the log file.
    """
    global _configured, _log_path

    app_dir = get_app_data_dir()
    logs_dir = os.path.join(app_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "birdstamp.log")
    _log_path = log_path

    if _configured:
        return log_path

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=1 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    # In a windowed (--windowed) PyInstaller build there is no console, so
    # sys.stdout / sys.stderr are None. A lot of libraries (uvicorn, click,
    # print(), etc.) assume they can write to / call methods on these streams,
    # which raises AttributeError on None. Replace them with a line-buffered
    # text stream that appends to the same log file.
    if sys.stdout is None or sys.stderr is None:
        stream = _LogFileStream(log_path)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream

    is_frozen = getattr(sys, "frozen", False)
    if not is_frozen:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        root_logger.addHandler(stream_handler)

    _configured = True
    return log_path


class _LogFileStream(io.TextIOWrapper):
    """A minimal, line-buffered, utf-8 text stream that appends to a file.

    Used to stand in for sys.stdout/sys.stderr when they are None (windowed
    PyInstaller build), so code that does print()/write()/flush()/isatty()
    on them doesn't crash.
    """

    def __init__(self, path):
        raw = open(path, "ab", buffering=0)
        super().__init__(raw, encoding="utf-8", line_buffering=True, write_through=True)

    def isatty(self):
        return False
