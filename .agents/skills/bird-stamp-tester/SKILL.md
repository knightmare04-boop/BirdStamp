---
name: bird-stamp-tester
description: Automated test suite, functional validation framework, and diagnostics engine for the Bird Stamp Collection application (FastAPI backend, React frontend, SQLite database, scraping, synchronization, and local Excel export).
---

# Bird Stamp Application Tester (`bird-stamp-tester`)

This skill provides a standardized, automated methodology and comprehensive test harness to verify every functionality and component of the Bird Stamp Collection application.

---

## Architecture Overview Under Test

1. **Backend REST API**: FastAPI application (`backend/main.py`) exposing pagination, full-text searching, multi-criteria filtering, CRUD operations on stamps, sync jobs, scraping, and Excel collection export.
2. **Database Layer**: SQLite (`backend/bird_stamps.db`) managed through SQLAlchemy ORM models (`backend/models.py`) and validated via Pydantic schemas (`backend/schemas.py`).
3. **Data Synchronization Engine**: Excel importer & matcher (`backend/sync.py`, `backend/fix_sync.py`, `backend/fix_sync_v2.py`) reading `My Collection_Final List_1.1.xlsx` and matching stamps across 5 heuristic levels.
4. **Philatelic Elements Engine**: Semantic classification pipeline (`backend/apply_elements.py`) linking stamps with `Philatelic Elements.xlsx` and `My collection element link.xlsx`.
5. **Web Scraper Engine**: Real-time parser (`backend/scraper.py`) targeting `birdtheme.org` country listings, issues, tables, and stamp imagery.
6. **Local Excel Export Engine**: Excel spreadsheet exporter (`backend/excel_export.py`) generating formatted `.xlsx` workbooks directly into the `"my collection sheets"` folder in the application directory.
7. **Frontend SPA**: React 19 + Vite application (`frontend/src/App.jsx`, `StampCard.jsx`) with live debounced filtering, modals, infinite/paginated browsing, and inline editing.
8. **Desktop Wrapper & Packaging**: PyWebView native window runtime (`backend/desktop.py`) packaged with PyInstaller (`build.py`, `BirdStamp.spec`).

---

## Test Execution Workflow

### 1. Running the Automated Diagnostic Suite
Execute the automated test script using the backend virtual environment:

```powershell
& "d:\Bird Project\backend\venv\Scripts\python.exe" "d:\Bird Project\.agents\skills\bird-stamp-tester\scripts\run_test_suite.py"
```

### 2. Testing Frontend Compilation & Assets
Execute build validation in the frontend workspace:

```powershell
cd "d:\Bird Project\frontend"
npm run build
```

### 3. Verification Checklist

- [ ] **Database Connectivity & Model Schema**: Verify table creation, column definitions (`id`, `country`, `year`, `face_value`, `english_name`, `scientific_name`, `bird_group`, `genus`, `species`, `category`, `stamp_type`, `release_date`, `image_url`, `my_collection`, `condition`, `duplicate`, `error`, `description`, `element_group`, `element`, `element_description`).
- [ ] **API Query & Filtering**:
  - GET `/api/stamps` default pagination (page=1, limit=100)
  - GET `/api/stamps?search=<query>` (case-insensitive English and Scientific name match)
  - GET `/api/stamps?country=<country>`
  - GET `/api/stamps?element_group=<group>`
  - GET `/api/stamps?element=<element>`
  - GET `/api/stamps?collection_status=owned|missing|all`
  - GET `/api/countries` (distinct sorted list)
  - GET `/api/options` (philatelic dropdown options)
- [ ] **API Mutations (CRUD)**:
  - PATCH `/api/stamps/{id}` (inline field updates)
  - POST `/api/stamps/{id}/duplicate` (cloning stamp data)
  - DELETE `/api/stamps/{id}` (record removal)
- [ ] **Background Processing & Status Tracking**:
  - GET `/api/status` (scrape and sync states)
  - POST `/api/sync` (background task dispatch)
  - POST `/api/scrape` (background task dispatch)
- [ ] **Data Matcher & Excel Sync**:
  - Level 1: Scientific Name + Face Value match
  - Level 2: English Name + Face Value match
  - Level 3: Face Value + Year match
  - Level 4: Scientific Name fallback
  - Level 5: English Name fallback
  - Prototype stamp cloning when duplicate entries occur
- [ ] **Philatelic Elements Mappings**:
  - Validation of `Philatelic Elements.xlsx` structure
  - Validation of `My collection element link.xlsx` condition mappings
- [ ] **Local Excel Export Engine**:
  - `excel_export.py` module loading
  - `my collection sheets` directory resolution
  - POST `/api/export` execution and `.xlsx` file generation with all 21 columns
- [ ] **Desktop Wrapper & Packaging**:
  - `desktop.py` entrypoint and PyWebView window creation
  - `build.py` PyInstaller command configuration and distribution bundling
