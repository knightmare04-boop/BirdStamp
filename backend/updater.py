"""Self-update from GitHub Releases.

How it works (frozen/packaged builds only):

1. Background check: shortly after the window opens, the app asks the GitHub
   API for the latest release of version.GITHUB_REPO. If its tag is newer than
   version.__version__, the app-only update zip (BirdStamp_Update-<ver>.zip) is
   downloaded, verified against its .sha256 asset, and extracted into
   <app dir>\\_update\\new. The UI then shows a "Restart to update" banner.

2. Apply: when the user clicks the banner (or on the next launch, if they
   chose "Later"), the app starts the *new* BirdStamp.exe from _update\\new
   with --apply-update and exits. That process waits for the old app to close,
   moves the old program files to _update\\old, copies the new ones in, and
   launches the updated app.

3. Health check / rollback: the updated app writes _update\\healthy once its
   window is up. If it exits before that, the apply process restores the old
   files, records the version in _update\\failed.json (so it is not retried),
   and relaunches the old version.

User data (bird_stamps.db, uploads, my collection sheets) is never touched:
only _internal, the exe, its .config and the bundled reference files are
replaced.
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile

from version import __version__, GITHUB_REPO

logger = logging.getLogger(__name__)

UPDATE_DIR_NAME = "_update"
ASSET_PREFIX = "BirdStamp_Update-"
STARTUP_DELAY_SECONDS = 5
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
PROCESS_EXIT_WAIT_SECONDS = 60
HEALTH_WAIT_SECONDS = 90
APPLY_HANDSHAKE_SECONDS = 30

# Program files replaced by an update, as (name in update, name in app dir).
# The exe name in the app dir may differ if the user renamed it.
EXTRA_FILES = ("README.txt", "Philatelic Elements.xlsx")

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

_lock = threading.Lock()
_state = {
    "current_version": __version__,
    # disabled|idle|checking|up_to_date|downloading|ready|error
    "status": "idle" if getattr(sys, "frozen", False) else "disabled",
    "latest_version": None,
    "notes": "",
    "message": "",
}
_restart_handler = None
_thread_started = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_version(text):
    """'v2.1.0' -> (2, 1, 0). Returns None if it can't be parsed."""
    if not text:
        return None
    text = str(text).strip().lstrip("vV")
    parts = []
    for piece in text.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts) if parts else None


def _is_newer(candidate, current=__version__):
    c, cur = parse_version(candidate), parse_version(current)
    return bool(c and cur and c > cur)


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def get_app_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def get_update_dir(app_dir=None):
    return os.path.join(app_dir or get_app_dir(), UPDATE_DIR_NAME)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _remove_file(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Could not remove %s", path, exc_info=True)


def _retry(fn, attempts=20, delay=0.5):
    """Retry a filesystem operation (OneDrive/antivirus can hold files briefly)."""
    last_exc = None
    for _ in range(attempts):
        try:
            return fn()
        except (PermissionError, OSError) as e:
            last_exc = e
            time.sleep(delay)
    raise last_exc


def _rmtree(path, attempts=10, delay=1.0):
    if not os.path.exists(path):
        return True
    for _ in range(attempts):
        try:
            shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            time.sleep(delay)
    logger.warning("Could not remove %s", path)
    return False


def _is_writable(directory):
    test_file = os.path.join(directory, ".update_write_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception:
        return False


def _failed_versions(update_dir):
    data = _read_json(os.path.join(update_dir, "failed.json")) or {}
    return set(data.get("versions", []))


def _record_failure(update_dir, version, reason):
    path = os.path.join(update_dir, "failed.json")
    data = _read_json(path) or {}
    versions = set(data.get("versions", []))
    versions.add(version)
    data["versions"] = sorted(versions)
    data.setdefault("reasons", {})[version] = reason
    try:
        _write_json(path, data)
    except Exception:
        logger.exception("Could not write %s", path)


def _set_state(**kwargs):
    with _lock:
        _state.update(kwargs)


def get_state():
    with _lock:
        return dict(_state)


# ---------------------------------------------------------------------------
# Public API used by desktop.py / main.py
# ---------------------------------------------------------------------------

def set_restart_handler(handler):
    """desktop.py registers a callable that launches the apply step and closes
    the window. Returns True if the restart was started."""
    global _restart_handler
    _restart_handler = handler


def request_restart():
    handler = _restart_handler
    if handler is None:
        return False
    try:
        return bool(handler())
    except Exception:
        logger.exception("Restart handler failed")
        return False


def staged_update_version():
    """Version of a downloaded, verified update waiting to be applied, or None."""
    if not is_frozen():
        return None
    update_dir = get_update_dir()
    ready = _read_json(os.path.join(update_dir, "ready.json")) or {}
    version = ready.get("version")
    if not version or not _is_newer(version):
        return None
    if version in _failed_versions(update_dir):
        return None
    if not os.path.isfile(os.path.join(update_dir, "new", "BirdStamp.exe")):
        return None
    return version


def launch_apply():
    """Start the staged exe in --apply-update mode. The caller must then exit."""
    version = staged_update_version()
    if not version:
        return False
    update_dir = get_update_dir()
    new_dir = os.path.join(update_dir, "new")
    staged_exe = os.path.join(new_dir, "BirdStamp.exe")
    args = [
        staged_exe,
        "--apply-update",
        "--app-dir", get_app_dir(),
        "--exe-name", os.path.basename(sys.executable),
        "--pid", str(os.getpid()),
        "--version", version,
    ]
    handshake_path = os.path.join(update_dir, "apply_started.json")
    _remove_file(handshake_path)
    try:
        proc = subprocess.Popen(
            args,
            cwd=new_dir,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception:
        logger.exception("Could not start the updater process")
        _record_failure(update_dir, version, "updater could not be started")
        _set_state(status="error", message="The update could not be installed.")
        return False

    # The staged exe must prove it can run before we exit. If it can't (e.g.
    # a broken download), give up on this version instead of closing the app.
    deadline = time.time() + APPLY_HANDSHAKE_SECONDS
    while time.time() < deadline:
        if os.path.exists(handshake_path):
            logger.info("Started updater for version %s; this instance will exit", version)
            return True
        if proc.poll() is not None:
            break
        time.sleep(0.25)

    logger.error("Updater for version %s did not start; skipping this version", version)
    try:
        proc.kill()
    except Exception:
        pass
    _record_failure(update_dir, version, "updater did not start")
    _set_state(status="error", message="The update could not be installed.")
    return False


def report_startup_failure():
    """Called when this app fails to start. If it was just installed by an
    update, tells the waiting apply process to roll back."""
    if not is_frozen():
        return
    update_dir = get_update_dir()
    applying = _read_json(os.path.join(update_dir, "applying.json"))
    if applying and applying.get("version") == __version__:
        try:
            _write_json(os.path.join(update_dir, "unhealthy.json"), {"version": __version__})
        except Exception:
            logger.exception("Could not write failure marker")


def mark_healthy():
    """Called by the app once its window is up. Tells a waiting apply process
    that the freshly installed version started fine."""
    if not is_frozen():
        return
    update_dir = get_update_dir()
    applying = _read_json(os.path.join(update_dir, "applying.json"))
    if applying and applying.get("version") == __version__:
        try:
            _write_json(os.path.join(update_dir, "healthy.json"), {"version": __version__})
            logger.info("Update to %s started successfully", __version__)
        except Exception:
            logger.exception("Could not write health marker")


def start_background_updater():
    """Start the periodic update check (packaged builds only)."""
    global _thread_started
    if _thread_started:
        return
    if not is_frozen() or os.environ.get("BIRDSTAMP_DISABLE_UPDATES"):
        _set_state(status="disabled", message="Automatic updates are only available in the installed app.")
        return
    if not _is_writable(get_app_dir()):
        _set_state(status="disabled", message="The app folder is read-only, so automatic updates are off.")
        logger.info("Updates disabled: app folder is not writable")
        return
    _thread_started = True
    threading.Thread(target=_update_loop, name="updater", daemon=True).start()


# ---------------------------------------------------------------------------
# Background check + download
# ---------------------------------------------------------------------------

def _release_api_url():
    # Override is only used for local testing of the update flow.
    return os.environ.get("BIRDSTAMP_UPDATE_URL") or (
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    )


def _http_headers():
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"BirdStamp/{__version__}",
    }


def _update_loop():
    time.sleep(STARTUP_DELAY_SECONDS)
    try:
        _cleanup()
    except Exception:
        logger.exception("Update cleanup failed")
    while True:
        try:
            _check_once()
        except Exception as e:
            logger.exception("Update check failed")
            _set_state(status="error", message=f"Update check failed: {e}")
        if get_state()["status"] == "ready":
            return
        time.sleep(CHECK_INTERVAL_SECONDS)


def _cleanup():
    """Remove leftovers from a previous (successful or abandoned) update."""
    update_dir = get_update_dir()
    if not os.path.isdir(update_dir):
        return

    applying_path = os.path.join(update_dir, "applying.json")
    healthy_path = os.path.join(update_dir, "healthy.json")
    applying = _read_json(applying_path)
    if applying and os.path.exists(healthy_path):
        _rmtree(os.path.join(update_dir, "old"))
        _remove_file(applying_path)
        _remove_file(healthy_path)
    elif not applying:
        # No install in progress: any backup is left over from a rollback.
        _rmtree(os.path.join(update_dir, "old"))

    ready_path = os.path.join(update_dir, "ready.json")
    ready = _read_json(ready_path) or {}
    version = ready.get("version")
    stale = (
        not version
        or not _is_newer(version)
        or version in _failed_versions(update_dir)
    )
    if stale:
        # The apply process may still be running from _update\new for a few
        # seconds after the new version starts, so retry the removal.
        if _rmtree(os.path.join(update_dir, "new"), attempts=20, delay=1.5):
            _remove_file(ready_path)

    _rmtree(os.path.join(update_dir, "download"))
    _remove_file(os.path.join(update_dir, "apply_started.json"))
    _remove_file(os.path.join(update_dir, "unhealthy.json"))


def _check_once():
    import requests

    update_dir = get_update_dir()
    _set_state(status="checking", message="")
    resp = requests.get(_release_api_url(), headers=_http_headers(), timeout=15)
    if resp.status_code == 404:
        _set_state(status="up_to_date", message="No releases published yet.")
        return
    resp.raise_for_status()
    release = resp.json()

    tag = release.get("tag_name", "")
    latest = tag.lstrip("vV")
    notes = release.get("body") or ""
    if not _is_newer(latest):
        _set_state(status="up_to_date", latest_version=latest, message="")
        return
    if latest in _failed_versions(update_dir):
        _set_state(
            status="error",
            latest_version=latest,
            message=f"Version {latest} could not be installed earlier and will be skipped.",
        )
        return
    if staged_update_version() == latest:
        _set_state(status="ready", latest_version=latest, notes=notes, message="")
        return

    assets = {a.get("name"): a.get("browser_download_url") for a in release.get("assets", [])}
    zip_name = f"{ASSET_PREFIX}{latest}.zip"
    zip_url = assets.get(zip_name)
    sha_url = assets.get(zip_name + ".sha256")
    if not zip_url or not sha_url:
        _set_state(
            status="error",
            latest_version=latest,
            message=f"Release {tag} has no {zip_name} (+ .sha256) asset.",
        )
        return

    _set_state(status="downloading", latest_version=latest, notes=notes, message="")
    logger.info("Downloading update %s", latest)
    _download_and_stage(requests, zip_url, sha_url, zip_name, latest, update_dir)
    _set_state(status="ready", latest_version=latest, notes=notes, message="")
    logger.info("Update %s is ready to install", latest)


def _download_and_stage(requests, zip_url, sha_url, zip_name, version, update_dir):
    download_dir = os.path.join(update_dir, "download")
    _rmtree(download_dir)
    os.makedirs(download_dir, exist_ok=True)

    sha_resp = requests.get(sha_url, headers={"User-Agent": _http_headers()["User-Agent"]}, timeout=30)
    sha_resp.raise_for_status()
    expected_sha = sha_resp.text.strip().split()[0].lower()

    zip_path = os.path.join(download_dir, zip_name)
    digest = hashlib.sha256()
    with requests.get(
        zip_url,
        headers={"User-Agent": _http_headers()["User-Agent"]},
        stream=True,
        timeout=(15, 120),
    ) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    digest.update(chunk)

    if digest.hexdigest().lower() != expected_sha:
        _rmtree(download_dir)
        raise RuntimeError("Downloaded update failed its checksum check")

    extract_dir = os.path.join(download_dir, "extracted")
    with zipfile.ZipFile(zip_path) as zf:
        root = os.path.realpath(extract_dir)
        for member in zf.namelist():
            target = os.path.realpath(os.path.join(extract_dir, member))
            if not (target == root or target.startswith(root + os.sep)):
                raise RuntimeError(f"Unsafe path in update zip: {member}")
        zf.extractall(extract_dir)

    if not (
        os.path.isfile(os.path.join(extract_dir, "BirdStamp.exe"))
        and os.path.isdir(os.path.join(extract_dir, "_internal"))
    ):
        raise RuntimeError("Update zip is missing BirdStamp.exe or _internal")

    new_dir = os.path.join(update_dir, "new")
    if not _rmtree(new_dir):
        raise RuntimeError("Could not clear the previous staged update")
    _retry(lambda: os.replace(extract_dir, new_dir))
    _write_json(os.path.join(update_dir, "ready.json"), {"version": version})
    _rmtree(download_dir)


# ---------------------------------------------------------------------------
# Apply step (runs inside the *new* exe, started with --apply-update)
# ---------------------------------------------------------------------------

def _wait_for_pid(pid, timeout_seconds):
    """True once the process has exited (or never existed)."""
    import ctypes

    SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        return True
    try:
        return kernel32.WaitForSingleObject(handle, int(timeout_seconds * 1000)) == WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


def _launch(exe_path):
    return subprocess.Popen(
        [exe_path],
        cwd=os.path.dirname(exe_path),
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def _parse_apply_args(argv):
    opts = {}
    it = iter(argv)
    for arg in it:
        if arg in ("--app-dir", "--exe-name", "--pid", "--version"):
            opts[arg[2:].replace("-", "_")] = next(it, None)
    missing = [k for k in ("app_dir", "exe_name", "pid", "version") if not opts.get(k)]
    if missing:
        raise ValueError(f"Missing updater arguments: {missing}")
    return opts


def run_apply(argv):
    """Entry point for `BirdStamp.exe --apply-update ...`. Returns an exit code."""
    try:
        opts = _parse_apply_args(argv)
    except Exception:
        logger.exception("[apply] Bad arguments: %s", argv)
        return 2

    app_dir = opts["app_dir"]
    exe_name = opts["exe_name"]
    version = opts["version"]
    update_dir = get_update_dir(app_dir)
    new_dir = os.path.join(update_dir, "new")
    old_dir = os.path.join(update_dir, "old")
    applying_path = os.path.join(update_dir, "applying.json")
    healthy_path = os.path.join(update_dir, "healthy.json")
    unhealthy_path = os.path.join(update_dir, "unhealthy.json")
    app_exe = os.path.join(app_dir, exe_name)

    # Handshake: lets the old app know this exe runs, so it can safely exit.
    try:
        _write_json(os.path.join(update_dir, "apply_started.json"), {"pid": os.getpid()})
    except Exception:
        logger.exception("[apply] Could not write handshake")
        return 1

    logger.info("[apply] Installing %s into %s", version, app_dir)

    if not _wait_for_pid(opts["pid"], PROCESS_EXIT_WAIT_SECONDS):
        logger.error("[apply] The running app did not exit; update postponed")
        return 1

    # (source in update, destination in app dir)
    program_files = [
        (os.path.join(new_dir, "_internal"), os.path.join(app_dir, "_internal")),
        (os.path.join(new_dir, "BirdStamp.exe"), app_exe),
        (os.path.join(new_dir, "BirdStamp.exe.config"), app_exe + ".config"),
    ]

    moved = []  # (backup path, original path)

    def restore():
        for _src, dest in program_files:
            if os.path.isdir(dest):
                _rmtree(dest)
            elif os.path.exists(dest):
                _remove_file(dest)
        for backup, original in reversed(moved):
            try:
                _retry(lambda b=backup, o=original: shutil.move(b, o))
            except Exception:
                logger.exception("[apply] Could not restore %s", original)

    try:
        _write_json(applying_path, {"version": version})
        _remove_file(healthy_path)
        _remove_file(unhealthy_path)
        if not _rmtree(old_dir):
            raise RuntimeError("Could not clear the previous backup folder")
        os.makedirs(old_dir, exist_ok=True)

        for _src, dest in program_files:
            if os.path.exists(dest):
                backup = os.path.join(old_dir, os.path.basename(dest))
                _retry(lambda d=dest, b=backup: shutil.move(d, b))
                moved.append((backup, dest))

        for src, dest in program_files:
            if os.path.isdir(src):
                _retry(lambda s=src, d=dest: shutil.copytree(s, d, dirs_exist_ok=True))
            elif os.path.isfile(src):
                _retry(lambda s=src, d=dest: shutil.copy2(s, d))
        for name in EXTRA_FILES:
            src = os.path.join(new_dir, name)
            if os.path.isfile(src):
                _retry(lambda s=src, d=os.path.join(app_dir, name): shutil.copy2(s, d))
    except Exception:
        logger.exception("[apply] Installing %s failed; restoring previous version", version)
        restore()
        _record_failure(update_dir, version, "install failed")
        _remove_file(applying_path)
        if os.path.isfile(app_exe):
            _launch(app_exe)
        return 1

    logger.info("[apply] Files installed; starting %s", app_exe)
    proc = _launch(app_exe)

    deadline = time.time() + HEALTH_WAIT_SECONDS
    while time.time() < deadline:
        if os.path.exists(healthy_path):
            logger.info("[apply] Version %s is running", version)
            return 0
        if os.path.exists(unhealthy_path) or proc.poll() is not None:
            break
        time.sleep(1)

    if os.path.exists(healthy_path):
        return 0
    if proc.poll() is None and not os.path.exists(unhealthy_path):
        logger.warning("[apply] %s is still starting after %ss; leaving it running", version, HEALTH_WAIT_SECONDS)
        return 0

    logger.error("[apply] Version %s failed during startup; rolling back", version)
    if proc.poll() is None:
        try:
            proc.kill()
            proc.wait(timeout=15)
        except Exception:
            logger.exception("[apply] Could not stop the failed version")
    _remove_file(unhealthy_path)
    restore()
    _record_failure(update_dir, version, "failed to start")
    _remove_file(applying_path)
    if os.path.isfile(app_exe):
        _launch(app_exe)
    return 1
