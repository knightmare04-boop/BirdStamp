import os
import subprocess
import shutil
import sqlite3
import stat
import sys
import zipfile


def run_command(cmd, cwd=None):
    print(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)


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


def build():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")
    backend_dir = os.path.join(root_dir, "backend")
    dist_dir = os.path.join(root_dir, "Distributions")

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

    # Only remove what this script owns/produces. Never touch other files
    # already in Distributions (e.g. V2.0.zip).
    force_delete(prepop_dir)
    force_delete(fresh_dir)
    for legacy in (fresh_zip, prepop_zip, legacy_zip):
        try:
            if os.path.exists(legacy):
                os.remove(legacy)
        except Exception as e:
            print(f"WARNING: Could not remove old zip {legacy}: {e}")

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
            "Logs:\n"
            "  If something goes wrong, check the log file at:\n"
            "  %LOCALAPPDATA%\\BirdStamp\\logs\\birdstamp.log\n"
        )
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_text)

    print("Copying to Fresh distribution...")
    shutil.copytree(build_output_dir, fresh_dir)
    if os.path.exists(philatelic_xlsx):
        shutil.copy2(philatelic_xlsx, fresh_dir)
    os.makedirs(os.path.join(fresh_dir, "my collection sheets"), exist_ok=True)
    os.makedirs(os.path.join(fresh_dir, "uploads"), exist_ok=True)
    _write_readme(fresh_dir)

    print("Copying to Prepopulated distribution...")
    shutil.copytree(build_output_dir, prepop_dir)
    if os.path.exists(philatelic_xlsx):
        shutil.copy2(philatelic_xlsx, prepop_dir)
    os.makedirs(os.path.join(prepop_dir, "my collection sheets"), exist_ok=True)
    os.makedirs(os.path.join(prepop_dir, "uploads"), exist_ok=True)
    _write_readme(prepop_dir)

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
    try:
        with zipfile.ZipFile(fresh_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(fresh_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, dist_dir)
                    zf.write(file_path, rel_path)
        print(f"Created {fresh_zip}")
    except Exception as e:
        print(f"FATAL: Failed to create {fresh_zip}: {e}")
        sys.exit(1)

    try:
        with zipfile.ZipFile(prepop_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(prepop_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, dist_dir)
                    zf.write(file_path, rel_path)
        print(f"Created {prepop_zip}")
    except Exception as e:
        print(f"FATAL: Failed to create {prepop_zip}: {e}")
        sys.exit(1)

    print("\n--- Build Complete ---")
    print(f"Distributions available in: {dist_dir}")


if __name__ == "__main__":
    build()
