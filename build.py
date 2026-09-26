import argparse
import hashlib
import os
import re
import subprocess
import shutil
import sqlite3
import stat
import sys
import zipfile

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(ROOT_DIR, "backend", "version.py")


def run_command(cmd, cwd=None):
    print(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)


def _capture(args, cwd=ROOT_DIR):
    """Run a command (list form) and return (returncode, stripped stdout)."""
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip()


def read_version_info():
    with open(VERSION_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    version = re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)
    repo = re.search(r'GITHUB_REPO\s*=\s*"([^"]+)"', text).group(1)
    return version, repo


def _version_tuple(text):
    return tuple(int(p) for p in re.findall(r"\d+", text or "")[:3])


def release_preflight(version, repo):
    """Refuse to publish unless the release would be reproducible and newer."""
    problems = []
    if shutil.which("gh") is None:
        problems.append("GitHub CLI (gh) is not installed.")
    elif _capture(["gh", "auth", "status"])[0] != 0:
        problems.append("GitHub CLI is not logged in (run: gh auth login).")

    code, status = _capture(["git", "status", "--porcelain"])
    if code != 0:
        problems.append("This folder is not a git repository.")
    elif status:
        problems.append("There are uncommitted changes. Commit them first so the release matches the code.")

    _capture(["git", "fetch", "--quiet"])
    _, head = _capture(["git", "rev-parse", "HEAD"])
    code, upstream = _capture(["git", "rev-parse", "@{u}"])
    if code != 0 or head != upstream:
        problems.append("Local commits are not pushed to GitHub. Run: git push")

    if shutil.which("gh") is not None:
        if _capture(["gh", "release", "view", f"v{version}", "--repo", repo])[0] == 0:
            problems.append(f"Release v{version} already exists. Bump __version__ in backend/version.py.")
        code, latest = _capture(
            ["gh", "release", "view", "--repo", repo, "--json", "tagName", "--jq", ".tagName"]
        )
        if code == 0 and latest and _version_tuple(latest) >= _version_tuple(version):
            problems.append(
                f"Version {version} is not newer than the latest release ({latest}). "
                "Bump __version__ in backend/version.py."
            )

    if problems:
        print("\nCannot publish a release:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    return head


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_dir(source_dir, zip_path, arc_root):
    """Zip source_dir; entries are stored under arc_root ('' for zip root)."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            if not dirs and not files and root != source_dir:
                # Keep empty folders (e.g. 'my collection sheets').
                rel_dir = os.path.relpath(root, source_dir)
                zf.write(root, (os.path.join(arc_root, rel_dir) if arc_root else rel_dir) + "/")
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, source_dir)
                zf.write(file_path, os.path.join(arc_root, rel_path) if arc_root else rel_path)


def force_delete(path):
    """Safely remove directories and files on Windows even with read-only attributes."""
    if not os.path.exists(path):
        return
    for root, dirs, files in os.walk(path, topdown=False):
        for f in files:
            fp = os.path.join(root, f)
            try:
                os.chmod(fp, stat.S_IWRITE)
                os.remove(fp)
            except Exception:
                pass
        for d in dirs:
            dp = os.path.join(root, d)
            try:
                os.chmod(dp, stat.S_IWRITE)
                os.rmdir(dp)
            except Exception:
                pass
    try:
        os.chmod(path, stat.S_IWRITE)
        os.rmdir(path)
    except Exception:
        pass


def _checkpoint_db(db_path):
    """Force a WAL checkpoint so the standalone .db file is self-contained.

    Returns True on success. If the database is locked (e.g. still open by a
    running instance), returns False so the build can abort instead of
    shipping a partial/inconsistent database.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.commit()
        finally:
            conn.close()
        return True
    except sqlite3.OperationalError as e:
        print(f"ERROR: Could not checkpoint bird_stamps.db ({e}). "
              "Is the app or another process still using it?")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error checkpointing bird_stamps.db: {e}")
        return False


def build(release=False, notes=None, notes_file=None):
    root_dir = ROOT_DIR
    frontend_dir = os.path.join(root_dir, "frontend")
    backend_dir = os.path.join(root_dir, "backend")
    dist_dir = os.path.join(root_dir, "Distributions")

    version, repo = read_version_info()
    print(f"=== BirdStamp {version} ===")
    release_commit = release_preflight(version, repo) if release else None

    print("--- 1. Building React Frontend ---")
    run_command("npm install", cwd=frontend_dir)
    run_command("npm run build", cwd=frontend_dir)

    print("--- 2. Packaging with PyInstaller ---")
    venv_python = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        print("ERROR: Virtual environment not found in backend/venv")
        sys.exit(1)

    frontend_dist_src = os.path.join(frontend_dir, "dist")

    add_data_args = [
        f"--add-data={frontend_dist_src};frontend_dist",
    ]

    philatelic_candidates = [
        os.path.join(root_dir, "data", "elements", "Philatelic Elements.xlsx"),
        os.path.join(root_dir, "Philatelic Elements.xlsx"),
    ]
    philatelic_xlsx = next((p for p in philatelic_candidates if os.path.exists(p)), philatelic_candidates[0])
    if os.path.exists(philatelic_xlsx):
        add_data_args.append(f"--add-data={philatelic_xlsx};.")

    runtime_hook = os.path.join(backend_dir, "rthook_unblock.py")

    pyinstaller_cmd = [
        venv_python, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",  # Don't show a console window
        "--noupx",
        "--name", "BirdStamp",
        "--runtime-hook", runtime_hook,
        "--hidden-import", "app_log",
        "--hidden-import", "updater",
        "--hidden-import", "version",
    ] + add_data_args + ["desktop.py"]

    cmd_str = " ".join(f'"{c}"' if " " in c or ";" in c else c for c in pyinstaller_cmd)
    run_command(cmd_str, cwd=backend_dir)

    build_output_dir = os.path.join(backend_dir, "dist", "BirdStamp")

    print("--- 3. Writing BirdStamp.exe.config (allow loading unsigned/remote-marked assemblies) ---")
    exe_config_path = os.path.join(build_output_dir, "BirdStamp.exe.config")
    exe_config_contents = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<configuration>\n'
        '  <runtime>\n'
        '    <loadFromRemoteSources enabled="true"/>\n'
        '  </runtime>\n'
        '</configuration>\n'
    )
    with open(exe_config_path, "w", encoding="utf-8") as f:
        f.write(exe_config_contents)

    print("--- 4. Preparing Distribution Folders ---")
    os.makedirs(dist_dir, exist_ok=True)

    prepop_dir = os.path.join(dist_dir, "BirdStamp_Prepopulated")
    fresh_dir = os.path.join(dist_dir, "BirdStamp_Fresh")
    prepop_zip = os.path.join(dist_dir, "BirdStamp_Prepopulated.zip")
    fresh_zip = os.path.join(dist_dir, "BirdStamp_Fresh.zip")
    legacy_zip = os.path.join(dist_dir, "birdstamp.zip")
    update_zip = os.path.join(dist_dir, f"BirdStamp_Update-{version}.zip")
    update_sha = update_zip + ".sha256"

    # Only remove what this script owns/produces. Never touch other files
    # already in Distributions (e.g. V2.0.zip).
    force_delete(prepop_dir)
    force_delete(fresh_dir)
    old_outputs = [fresh_zip, prepop_zip, legacy_zip] + [
        os.path.join(dist_dir, name)
        for name in os.listdir(dist_dir)
        if name.startswith("BirdStamp_Update-")
    ]
    for legacy in old_outputs:
        try:
            if os.path.exists(legacy):
                os.remove(legacy)
        except Exception as e:
            print(f"WARNING: Could not remove old file {legacy}: {e}")

    def _write_readme(target_dir):
        readme_path = os.path.join(target_dir, "README.txt")
        readme_text = (
            "BirdStamp Tracker\n"
            "=================\n\n"
            "How to start:\n"
            "  Double-click BirdStamp.exe.\n\n"
            "If Windows says the app is blocked, or it fails to start:\n"
            "  The app was likely downloaded as a zip, which Windows marks as\n"
            "  'from the internet'. Before extracting, right-click the zip file,\n"
            "  choose Properties, check the 'Unblock' box near the bottom, then\n"
            "  click OK and extract again.\n\n"
            "  If you already extracted it, open PowerShell in this folder and run:\n"
            "      Get-ChildItem -Recurse | Unblock-File\n"
            "  then start BirdStamp.exe again.\n\n"
            "Requirements:\n"
            "  - Windows 10 or 11\n"
            "  - .NET Framework 4.8\n"
            "  - Microsoft Edge WebView2 Runtime\n\n"
            "Updates:\n"
            "  The app checks for new versions automatically. When one is ready,\n"
            "  a banner offers to restart and install it. Your collection data\n"
            "  (bird_stamps.db, uploads, my collection sheets) is never replaced.\n\n"
            "Logs:\n"
            "  If something goes wrong, check the log file at:\n"
            "  %LOCALAPPDATA%\\BirdStamp\\logs\\birdstamp.log\n"
        )
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_text)

    # Program files shared by every distribution and by the update package.
    if os.path.exists(philatelic_xlsx):
        shutil.copy2(philatelic_xlsx, build_output_dir)
    _write_readme(build_output_dir)

    print("Copying to Fresh distribution...")
    shutil.copytree(build_output_dir, fresh_dir)
    os.makedirs(os.path.join(fresh_dir, "my collection sheets"), exist_ok=True)
    os.makedirs(os.path.join(fresh_dir, "uploads"), exist_ok=True)

    print("Copying to Prepopulated distribution...")
    shutil.copytree(build_output_dir, prepop_dir)
    os.makedirs(os.path.join(prepop_dir, "my collection sheets"), exist_ok=True)
    os.makedirs(os.path.join(prepop_dir, "uploads"), exist_ok=True)

    original_db = os.path.join(backend_dir, "bird_stamps.db")
    if os.path.exists(original_db):
        print("Checkpointing bird_stamps.db WAL before copying...")
        if not _checkpoint_db(original_db):
            print("FATAL: Aborting build - refusing to ship a partial/locked database.")
            sys.exit(1)
        shutil.copy2(original_db, prepop_dir)
        print("Copied updated bird_stamps.db to Prepopulated distribution.")
    else:
        print("WARNING: bird_stamps.db not found in backend folder. Prepopulated will be empty.")

    backend_uploads = os.path.join(backend_dir, "uploads")
    if os.path.exists(backend_uploads):
        for uf in os.listdir(backend_uploads):
            uf_src = os.path.join(backend_uploads, uf)
            if os.path.isfile(uf_src):
                shutil.copy2(uf_src, os.path.join(prepop_dir, "uploads", uf))

    print("--- 5. Creating Distribution Zips ---")
    for source_dir, zip_path, arc_root in (
        (fresh_dir, fresh_zip, "BirdStamp_Fresh"),
        (prepop_dir, prepop_zip, "BirdStamp_Prepopulated"),
        # App-only package used by the auto-updater: program files at the
        # zip root, no database or user folders.
        (build_output_dir, update_zip, ""),
    ):
        try:
            _zip_dir(source_dir, zip_path, arc_root)
            print(f"Created {zip_path}")
        except Exception as e:
            print(f"FATAL: Failed to create {zip_path}: {e}")
            sys.exit(1)

    with open(update_sha, "w", encoding="utf-8") as f:
        f.write(f"{_sha256(update_zip)}  {os.path.basename(update_zip)}\n")
    print(f"Created {update_sha}")

    print("\n--- Build Complete ---")
    print(f"Distributions available in: {dist_dir}")

    if release:
        print(f"\n--- 6. Publishing GitHub release v{version} ---")
        gh_cmd = [
            "gh", "release", "create", f"v{version}",
            update_zip, update_sha, prepop_zip, fresh_zip,
            "--repo", repo,
            "--target", release_commit,
            "--title", f"BirdStamp {version}",
        ]
        if notes_file:
            gh_cmd += ["--notes-file", notes_file]
        elif notes:
            gh_cmd += ["--notes", notes]
        else:
            gh_cmd += ["--generate-notes"]
        print("Uploading release assets (this can take a few minutes)...")
        result = subprocess.run(gh_cmd, cwd=root_dir)
        if result.returncode != 0:
            print("FATAL: Publishing the release failed.")
            sys.exit(1)
        print(f"Published v{version}. Installed copies will pick it up automatically.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build BirdStamp distributions.")
    parser.add_argument(
        "--release",
        action="store_true",
        help="Also publish a GitHub release so installed apps auto-update.",
    )
    parser.add_argument("--notes", help="Release notes text (shown on GitHub).")
    parser.add_argument("--notes-file", help="Path to a file with release notes.")
    args = parser.parse_args()
    build(release=args.release, notes=args.notes, notes_file=args.notes_file)
