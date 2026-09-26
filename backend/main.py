from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel
import os
import sys
import uuid
import time
import base64
import binascii
import logging

import models
import schemas
from database import engine, get_db, ensure_db_schema, get_uploads_dir, SessionLocal
import scraper
import sync
import philatelic_data
import updater
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Run auto-migration on startup
ensure_db_schema()
models.Base.metadata.create_all(bind=engine)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB

EXCEL_FILENAME = "My Collection_Final List_1.1.xlsx"

def _default_excel_path() -> Optional[str]:
    """Locate the default collection workbook. No CWD-relative paths."""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(exe_dir, EXCEL_FILENAME),
            os.path.join(exe_dir, "data", "collections", EXCEL_FILENAME),
        ]
    else:
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(project_dir, "data", "collections", EXCEL_FILENAME),
            os.path.join(project_dir, EXCEL_FILENAME),
        ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

def _run_sync_job(excel_path: str):
    """Background job wrapper: owns its own session, independent of any request-scoped session."""
    db = SessionLocal()
    try:
        sync.run_sync(excel_path, db)
    finally:
        db.close()

def _run_scrape_job():
    """Background/scheduled job wrapper: owns its own session, independent of any request-scoped session."""
    db = SessionLocal()
    try:
        scraper.run_scrape(db)
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_scrape_job, 'cron', day=1, hour=2, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Bird Stamp Collection API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

uploads_dir = get_uploads_dir()
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

class Base64ImageUpload(BaseModel):
    image_data: str
    filename: Optional[str] = "specimen.jpg"

@app.get("/api/stamps", response_model=schemas.PaginatedResponse[schemas.Stamp])
def get_stamps(
    page: int = 1,
    limit: int = 100, 
    search: Optional[str] = None, 
    country: Optional[str] = None, 
    collection_status: str = 'all', 
    element_group: Optional[str] = None,
    element: Optional[str] = None,
    bird_group: Optional[str] = None,
    genus: Optional[str] = None,
    species: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Stamp)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                models.Stamp.english_name.ilike(search_term),
                models.Stamp.scientific_name.ilike(search_term),
                models.Stamp.bird_group.ilike(search_term),
                models.Stamp.genus.ilike(search_term),
                models.Stamp.species.ilike(search_term)
            )
        )
        
    if country:
        query = query.filter(models.Stamp.country.ilike(f"%{country}%"))
        
    if element_group:
        query = query.filter(models.Stamp.element_group.ilike(f"%{element_group}%"))
        
    if element:
        query = query.filter(models.Stamp.element.ilike(f"%{element}%"))

    if bird_group:
        query = query.filter(models.Stamp.bird_group.ilike(f"%{bird_group}%"))

    if genus:
        query = query.filter(models.Stamp.genus.ilike(f"%{genus}%"))

    if species:
        query = query.filter(models.Stamp.species.ilike(f"%{species}%"))
        
    if collection_status == 'owned':
        query = query.filter(models.Stamp.my_collection.is_(True))
    elif collection_status == 'missing':
        query = query.filter(models.Stamp.my_collection.is_(False))
        
    total = query.count()
    stamps = query.offset((page - 1) * limit).limit(limit).all()
    
    return {
        "items": stamps,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/countries", response_model=List[str])
def get_countries(db: Session = Depends(get_db)):
    countries = db.query(models.Stamp.country).filter(models.Stamp.country.isnot(None), models.Stamp.country != "").distinct().order_by(models.Stamp.country).all()
    return [c[0] for c in countries]

@app.get("/api/options", response_model=schemas.PhilatelicOptions)
def get_options():
    """Retrieve dropdown options for Condition, Element Groups, and Elements with descriptions."""
    return philatelic_data.get_philatelic_options()

@app.patch("/api/stamps/{stamp_id}", response_model=schemas.Stamp)
def update_stamp(stamp_id: int, stamp: schemas.StampUpdate, db: Session = Depends(get_db)):
    db_stamp = db.query(models.Stamp).filter(models.Stamp.id == stamp_id).first()
    if not db_stamp:
        raise HTTPException(status_code=404, detail="Stamp not found")
    
    update_data = stamp.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_stamp, key, value)
        
    db.commit()
    db.refresh(db_stamp)
    return db_stamp

@app.post("/api/stamps/{stamp_id}/duplicate", response_model=schemas.Stamp)
def duplicate_stamp(stamp_id: int, db: Session = Depends(get_db)):
    db_stamp = db.query(models.Stamp).filter(models.Stamp.id == stamp_id).first()
    if not db_stamp:
        raise HTTPException(status_code=404, detail="Stamp not found")
    
    new_stamp = models.Stamp(
        country=db_stamp.country,
        year=db_stamp.year,
        face_value=db_stamp.face_value,
        english_name=db_stamp.english_name,
        scientific_name=db_stamp.scientific_name,
        bird_group=db_stamp.bird_group,
        genus=db_stamp.genus,
        species=db_stamp.species,
        category=db_stamp.category,
        stamp_type=db_stamp.stamp_type,
        release_date=db_stamp.release_date,
        image_url=db_stamp.image_url,
        my_collection=db_stamp.my_collection,
        condition=db_stamp.condition,
        duplicate=db_stamp.duplicate,
        error=db_stamp.error,
        description=db_stamp.description,
        element_group=db_stamp.element_group,
        element=db_stamp.element,
        element_description=db_stamp.element_description,
    )
    db.add(new_stamp)
    db.commit()
    db.refresh(new_stamp)
    return new_stamp

@app.delete("/api/stamps/{stamp_id}")
def delete_stamp(stamp_id: int, db: Session = Depends(get_db)):
    db_stamp = db.query(models.Stamp).filter(models.Stamp.id == stamp_id).first()
    if not db_stamp:
        raise HTTPException(status_code=404, detail="Stamp not found")
    
    db.delete(db_stamp)
    db.commit()
    return {"message": "Stamp deleted"}

@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    filename = file.filename or "specimen.jpg"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]:
        ext = ".jpg"
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 15MB)")
    unique_filename = f"specimen_{uuid.uuid4().hex[:10]}_{int(time.time())}{ext}"
    dest_path = os.path.join(uploads_dir, unique_filename)
    with open(dest_path, "wb") as f:
        f.write(content)
    return {
        "status": "success",
        "image_url": f"/uploads/{unique_filename}",
        "filename": unique_filename
    }

@app.post("/api/upload-image-base64")
def upload_image_base64(data: Base64ImageUpload):
    raw_data = data.image_data
    if "," in raw_data:
        raw_data = raw_data.split(",", 1)[1]

    # Preliminary guard on the encoded string length before decoding (base64 inflates size ~4/3)
    if len(raw_data) > (MAX_UPLOAD_BYTES * 4 // 3) + 8:
        raise HTTPException(status_code=413, detail="Image too large (max 15MB)")

    try:
        image_bytes = base64.b64decode(raw_data, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 15MB)")

    ext = os.path.splitext(data.filename or "specimen.jpg")[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]:
        ext = ".jpg"
    unique_filename = f"specimen_{uuid.uuid4().hex[:10]}_{int(time.time())}{ext}"
    dest_path = os.path.join(uploads_dir, unique_filename)
    with open(dest_path, "wb") as f:
        f.write(image_bytes)
    return {
        "status": "success",
        "image_url": f"/uploads/{unique_filename}",
        "filename": unique_filename
    }

@app.post("/api/stamps", response_model=schemas.Stamp)
def create_stamp(stamp_data: schemas.StampCreate, db: Session = Depends(get_db)):
    # Auto-derive genus and species from scientific name if left blank
    genus = (stamp_data.genus or "").strip()
    species = (stamp_data.species or "").strip()
    sci_name = (stamp_data.scientific_name or "").strip()
    if sci_name and (not genus or not species):
        parts = sci_name.split()
        if not genus and len(parts) >= 1:
            genus = parts[0]
        if not species and len(parts) >= 2:
            species = parts[1]

    new_stamp = models.Stamp(
        country=(stamp_data.country or "").strip(),
        year=str(stamp_data.year or "").strip(),
        face_value=(stamp_data.face_value or "").strip(),
        english_name=(stamp_data.english_name or "").strip(),
        scientific_name=sci_name,
        bird_group=(stamp_data.bird_group or "").strip(),
        genus=genus,
        species=species,
        category=(stamp_data.category or "").strip(),
        stamp_type=(stamp_data.stamp_type or "").strip(),
        release_date=(stamp_data.release_date or "").strip(),
        image_url=(stamp_data.image_url or "").strip(),
        my_collection=True if stamp_data.my_collection is None else bool(stamp_data.my_collection),
        condition=(stamp_data.condition or "").strip(),
        duplicate=(stamp_data.duplicate or "no").strip(),
        error=(stamp_data.error or "").strip(),
        description=(stamp_data.description or "").strip(),
        element_group=(stamp_data.element_group or "").strip(),
        element=(stamp_data.element or "").strip(),
        element_description=(stamp_data.element_description or "").strip()
    )
    db.add(new_stamp)
    db.commit()
    db.refresh(new_stamp)
    return new_stamp

class SyncRequest(BaseModel):
    excel_path: Optional[str] = None

@app.post("/api/sync")
def trigger_excel_sync(background_tasks: BackgroundTasks, body: Optional[SyncRequest] = None):
    if sync.sync_state["is_running"] or scraper.scrape_state["is_running"]:
        raise HTTPException(status_code=409, detail="A sync or scrape is already running")

    provided_path = body.excel_path if body else None
    if provided_path:
        if not os.path.isfile(provided_path) or not provided_path.lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail=f"Excel file not found or not a .xlsx file: {provided_path}")
        excel_path = provided_path
    else:
        excel_path = _default_excel_path()
        if not excel_path:
            raise HTTPException(status_code=400, detail="No Excel file was provided and no default workbook was found. Please choose the Excel file.")

    # Set synchronously (before scheduling) to close the double-click race window.
    sync.sync_state["is_running"] = True
    background_tasks.add_task(_run_sync_job, excel_path)
    return {"message": "Sync started in background"}

@app.post("/api/scrape")
def trigger_scrape(background_tasks: BackgroundTasks):
    if sync.sync_state["is_running"] or scraper.scrape_state["is_running"]:
        raise HTTPException(status_code=409, detail="A sync or scrape is already running")

    scraper.scrape_state["is_running"] = True
    background_tasks.add_task(_run_scrape_job)
    return {"message": "Scraping started in background"}

@app.get("/api/status")
def get_status():
    return {
        "scrape": scraper.scrape_state,
        "sync": sync.sync_state
    }

@app.get("/api/update")
def get_update_status():
    return updater.get_state()

@app.post("/api/update/apply")
def apply_update():
    if updater.get_state()["status"] != "ready":
        raise HTTPException(status_code=409, detail="No update is ready to install.")
    if not updater.request_restart():
        raise HTTPException(
            status_code=500,
            detail="The update could not be installed. You can keep using this version.",
        )
    return {"message": "Restarting to install the update"}

@app.post("/api/export")
@app.post("/api/backup")
def trigger_export(db: Session = Depends(get_db)):
    import excel_export
    try:
        result = excel_export.export_collection_to_excel(db)
        return {
            "message": result.get("message", "Export successful"),
            "folder": result.get("folder"),
            "filename": result.get("filename"),
            "file_path": result.get("file_path"),
            "total_stamps": result.get("total_stamps")
        }
    except Exception as e:
        logger.exception("Export failed")
        raise HTTPException(status_code=500, detail=str(e))

if getattr(sys, 'frozen', False):
    frontend_path = os.path.join(sys._MEIPASS, "frontend_dist")
else:
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(frontend_path):
    assets_path = os.path.join(frontend_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")

        frontend_root = os.path.realpath(frontend_path)
        file_path = os.path.realpath(os.path.join(frontend_path, full_path))
        is_within_root = file_path == frontend_root or file_path.startswith(frontend_root + os.sep)
        if is_within_root and os.path.isfile(file_path):
            return FileResponse(file_path)

        return FileResponse(os.path.join(frontend_path, "index.html"))
