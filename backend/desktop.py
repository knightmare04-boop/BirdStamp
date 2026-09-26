"""Desktop entry point for BirdStamp Tracker.

Logging must be set up before anything else is imported, so that import
errors (missing DLLs, blocked assemblies, etc.) end up in the log file
instead of vanishing into a windowed build with no console.
"""
import sys

from app_log import setup_logging, get_app_data_dir

log_path = setup_logging()

import ctypes
import logging
import os
import socket
import threading
import time
import traceback

logger = logging.getLogger(__name__)

MB_ICONERROR = 0x10
MB_OK = 0x0

MIN_NET_RELEASE = 461808  # .NET Framework 4.7.2


def _report_startup_failure():
    """If this version was just installed by an update, trigger a rollback."""
    try:
        import updater

        updater.report_startup_failure()
    except Exception:
        logger.exception("Could not report startup failure to the updater")


def _show_error(title, message):
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, MB_ICONERROR | MB_OK)
    except Exception:
        logger.exception("Failed to display MessageBoxW for: %s", title)


def _check_dotnet_framework():
    """Returns True if .NET Framework 4.7.2+ is installed (Windows only)."""
    if sys.platform != "win32":
        return True

    try:
        import winreg

        key_path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            release, _ = winreg.QueryValueEx(key, "Release")
    except FileNotFoundError:
        release = None
    except OSError:
        release = None

    if release is None or release < MIN_NET_RELEASE:
        logger.error(
            ".NET Framework check failed: Release=%s (need >= %s)",
            release,
            MIN_NET_RELEASE,
        )
        _show_error(
            "BirdStamp Tracker - Missing Requirement",
            "BirdStamp Tracker requires .NET Framework 4.7.2 or newer "
            "(4.8 recommended), which was not found on this computer.\n\n"
            "Please install it from:\n"
            "https://dotnet.microsoft.com/download/dotnet-framework/net48\n\n"
            "Then run BirdStamp Tracker again.\n\n"
            f"Log file: {log_path}",
        )
        return False

    return True


def _find_free_port(preferred=8000, host="127.0.0.1"):
    """Try the preferred port first; fall back to an OS-assigned free port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, preferred))
        s.close()
        return preferred
    except OSError:
        s.close()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_server(port, host="127.0.0.1"):
    import uvicorn
    from main import app

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,
        use_colors=False,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server.run()


def _wait_for_server(port, host="127.0.0.1", timeout=20.0):
    import urllib.request
    import urllib.error

    url = f"http://{host}:{port}/api/status"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


class Api:
    """js_api object exposed to the frontend as window.pywebview.api."""

    def __init__(self):
        # Leading underscore keeps pywebview from trying to expose/serialize
        # this attribute (see webview.util.get_functions: names starting
        # with '_' are skipped).
        self._window = None

    def pick_excel(self):
        try:
            import webview

            dialog_type = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
            if dialog_type is None:
                dialog_type = getattr(webview, "OPEN_DIALOG", 10)

            window = self._window
            if window is None:
                logger.error("pick_excel called before window was set")
                return None

            result = window.create_file_dialog(
                dialog_type,
                allow_multiple=False,
                file_types=("Excel files (*.xlsx)",),
            )
            if not result:
                return None
            if isinstance(result, (list, tuple)):
                return result[0] if result else None
            return result
        except Exception:
            logger.exception("pick_excel failed")
            return None


def _on_gui_started():
    import updater

    logger.info("BirdStamp GUI started")
    updater.mark_healthy()
    updater.start_background_updater()


_restarting_for_update = False


def _make_restart_handler(window):
    import updater

    def _restart_for_update():
        global _restarting_for_update
        if not updater.launch_apply():
            return False
        _restarting_for_update = True

        def _close_window():
            # Give the HTTP response a moment to reach the page first.
            time.sleep(0.5)
            try:
                window.destroy()
            except Exception:
                logger.exception("Could not close the window for the update; exiting")
                os._exit(0)

        threading.Thread(target=_close_window, daemon=True).start()
        return True

    return _restart_for_update


def main():
    import updater
    from version import __version__

    logger.info("BirdStamp %s starting", __version__)

    # An update downloaded in an earlier session (user chose "Later") is
    # installed now, before anything else starts.
    if updater.staged_update_version() and updater.launch_apply():
        return

    if not _check_dotnet_framework():
        sys.exit(1)

    port = _find_free_port(8000)
    logger.info("Starting backend server on 127.0.0.1:%s", port)

    def _run_server():
        try:
            _start_server(port)
        except Exception:
            logger.exception("Backend server thread crashed")

    server_thread = threading.Thread(target=_run_server, daemon=True, name="uvicorn-server")
    server_thread.start()

    if not _wait_for_server(port):
        logger.error("Backend server did not become ready in time")
        _report_startup_failure()
        _show_error(
            "BirdStamp Tracker - Startup Failed",
            "BirdStamp Tracker's background server did not start in time.\n\n"
            f"Log file: {log_path}",
        )
        sys.exit(1)

    import webview

    api = Api()
    window = webview.create_window(
        "BirdStamp Tracker",
        f"http://127.0.0.1:{port}",
        width=1200,
        height=800,
        min_size=(800, 600),
        js_api=api,
    )
    api._window = window
    updater.set_restart_handler(_make_restart_handler(window))

    storage_path = os.path.join(get_app_data_dir(), "webview")

    try:
        webview.start(
            func=_on_gui_started,
            private_mode=False,
            storage_path=storage_path,
        )
    except Exception:
        logger.error("BirdStamp GUI failed\n%s", traceback.format_exc())
        _report_startup_failure()
        _show_error(
            "BirdStamp Tracker - Startup Failed",
            "The application window component could not start.\n\n"
            "The most common cause is Windows blocking files that came from "
            "a downloaded zip archive. To fix this:\n"
            "  1. Right-click the downloaded zip file > Properties > check "
            "'Unblock' > OK, then extract it again.\n"
            "  OR run this in PowerShell inside the app folder:\n"
            "     Get-ChildItem -Recurse | Unblock-File\n\n"
            "Also make sure these are installed:\n"
            "  - .NET Framework 4.8: "
            "https://dotnet.microsoft.com/download/dotnet-framework/net48\n"
            "  - Microsoft Edge WebView2 Runtime: "
            "https://go.microsoft.com/fwlink/p/?LinkId=2124703\n\n"
            f"Log file: {log_path}",
        )
        sys.exit(1)

    if _restarting_for_update:
        # Exit straight away so the updater can replace our files.
        logger.info("Exiting to install update")
        logging.shutdown()
        os._exit(0)


if __name__ == "__main__":
    if "--apply-update" in sys.argv:
        # Running from _update\new as the updater: swap in the new files and
        # relaunch. Never starts the server or the window.
        import updater

        try:
            code = updater.run_apply(sys.argv[1:])
        except Exception:
            logger.exception("Updater crashed")
            code = 1
        logging.shutdown()
        sys.exit(code)

    try:
        main()
    except SystemExit:
        raise
    except Exception:
        logger.error("Unhandled exception in desktop.py\n%s", traceback.format_exc())
        _report_startup_failure()
        _show_error(
            "BirdStamp Tracker - Startup Failed",
            "BirdStamp Tracker failed to start due to an unexpected error.\n\n"
            f"Log file: {log_path}",
        )
        sys.exit(1)
