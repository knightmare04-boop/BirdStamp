# Bird Stamp Collection

A complete desktop application for bird stamp collectors. Built with a FastAPI backend, SQLite database with WAL mode, and a modern React (Vite + Tailwind) frontend, bundled into standalone Windows executables with PyInstaller and PyWebView.

---

## Project Structure

```
d:\Bird Project\
├── start.bat                   # 1-Click launcher (installs dependencies, builds frontend, launches app)
├── build.py                    # Build script for PyInstaller standalone executables & distribution zip
├── backend/                    # FastAPI backend, SQLite database, and sync/export engines
│   ├── main.py                 # FastAPI application entrypoint and API routes
│   ├── desktop.py              # PyWebView desktop window launcher
│   ├── database.py             # SQLite connection, WAL mode, schema auto-migration
│   ├── excel_export.py         # Full collection Excel exporter
│   ├── philatelic_data.py      # Philatelic elements and groups loader
│   ├── scraper.py              # Bird stamp web scraper
│   ├── sync.py                 # Collection Excel synchronization engine
│   └── bird_stamps.db          # SQLite database
├── frontend/                   # React + Vite frontend application
│   ├── src/                    # UI components, filters, views, styles
│   └── dist/                   # Production build assets
├── data/                       # Categorized source data and reference spreadsheets
│   ├── collections/            # Primary stamp collection datasets (e.g. My Collection_Final List_1.1.xlsx)
│   ├── elements/               # Philatelic element taxonomies and mapping spreadsheets
│   └── ioc_reference/          # IOC World Bird List official reference files (v15.2)
├── Distributions/              # Standalone Windows distribution builds
│   ├── BirdStamp_Fresh/        # Clean build with empty/fresh database
│   ├── BirdStamp_Prepopulated/ # Build pre-seeded with current bird_stamps.db
│   ├── BirdStamp_Fresh.zip     # Release zip (fresh)
│   └── BirdStamp_Prepopulated.zip # Release zip (prepopulated)
├── my collection sheets/       # Default folder for user-exported Excel collection sheets
└── .agents/                    # Workspace agent tools, skills, and test suites
```

---

## Getting Started

### Quick Launch
Simply double-click **`start.bat`** in the root directory. It will:
1. Verify and install frontend npm dependencies.
2. Compile the React frontend production bundle.
3. Verify the Python virtual environment and backend dependencies.
4. Launch the desktop application window.

### Creating Desktop Builds
Run:
```powershell
.\backend\venv\Scripts\python.exe build.py
```
This builds standalone executables in `Distributions/BirdStamp_Fresh` and `Distributions/BirdStamp_Prepopulated`, and packages `Distributions/BirdStamp_Fresh.zip` and `Distributions/BirdStamp_Prepopulated.zip`.

Each build ships a `BirdStamp.exe.config` (`loadFromRemoteSources`) and a runtime hook (`backend/rthook_unblock.py`) so the app still starts when Windows marks the extracted files as downloaded from the internet. Runtime logs: `%LOCALAPPDATA%\BirdStamp\logs\birdstamp.log`.

It also produces `Distributions/BirdStamp_Update-<version>.zip` (+ `.sha256`), the app-only package used by auto-update.

### Publishing an Update (auto-update)
Installed copies of the app check this repo's latest GitHub Release in the background. When a newer version is found, it is downloaded and verified, and the app shows a **Restart to update** banner (or installs it on the next launch). Only program files are replaced; `bird_stamps.db`, `uploads/` and `my collection sheets/` are never touched. If the new version fails to start, the app rolls back to the previous one automatically.

To ship an update:
1. Bump `__version__` in `backend/version.py` (e.g. `2.1.0` → `2.2.0`).
2. Commit and push your changes.
3. Run:
   ```powershell
   .\backend\venv\Scripts\python.exe build.py --release --notes "What changed in this version"
   ```
   This builds everything and publishes release `v<version>` on GitHub with the update package and both full zips. It refuses to publish if there are uncommitted or unpushed changes, or if the version isn't newer than the latest release.

Updates are off when running from source, and when the app folder is read-only (e.g. installed under Program Files).

---

## Features

- **"Create Card" Feature**: Manually catalog custom bird stamps outside the scraper. Upload specimen photographs directly (PNG, JPG, WEBP, GIF), record comprehensive taxonomy (bird group, genus, species), set philatelic classifications (element group, element), specify conditions and collection statuses, and persist records in SQLite.
- **Search & Filter**: Real-time debounce searching across English names, scientific names, bird groups, countries, and philatelic elements.
- **Excel Export**: Export full collections with all 21 metadata fields directly into `my collection sheets/`.
- **Theme Switcher**: Smooth animated transition between Espresso Dark and Parchment Light themes.

