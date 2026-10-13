import os
import sys
import logging
import sqlite3
import pandas as pd
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

import models
from database import get_database_path, ensure_db_schema

logger = logging.getLogger(__name__)

EXCEL_FILENAME = "My Collection_Final List_1.1.xlsx"
SEED_DB_FILENAME = "taxonomy_reference.db"

def get_seed_db_path() -> Optional[str]:
    """Find pre-compiled taxonomy_reference.db in development or packaged environments."""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(exe_dir, "data", "collections", SEED_DB_FILENAME),
            os.path.join(exe_dir, SEED_DB_FILENAME),
            os.path.join(getattr(sys, '_MEIPASS', ''), "data", "collections", SEED_DB_FILENAME),
            os.path.join(getattr(sys, '_MEIPASS', ''), SEED_DB_FILENAME),
        ]
    else:
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(project_dir, "data", "collections", SEED_DB_FILENAME),
            os.path.join(project_dir, "backend", SEED_DB_FILENAME),
        ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None

def get_excel_path() -> Optional[str]:
    """Find My Collection_Final List_1.1.xlsx in development or packaged environments."""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(exe_dir, EXCEL_FILENAME),
            os.path.join(exe_dir, "data", "collections", EXCEL_FILENAME),
            os.path.join(getattr(sys, '_MEIPASS', ''), "data", "collections", EXCEL_FILENAME),
            os.path.join(getattr(sys, '_MEIPASS', ''), EXCEL_FILENAME),
        ]
    else:
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(project_dir, "data", "collections", EXCEL_FILENAME),
            os.path.join(project_dir, EXCEL_FILENAME),
        ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None

def clean_val(val: Any) -> str:
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

def populate_taxonomy_from_seed(seed_path: str, db_path: str) -> bool:
    """Instant population of taxonomy_reference from pre-compiled seed database (< 0.05s)."""
    if not os.path.exists(seed_path):
        return False
    try:
        ensure_db_schema()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM taxonomy_reference;")
        cursor.execute(f"ATTACH DATABASE '{seed_path}' AS seed_db;")
        cursor.execute("""
            INSERT INTO taxonomy_reference (
                english_name, scientific_name, "order", family, bird_group, genus, species
            )
            SELECT english_name, scientific_name, "order", family, bird_group, genus, species
            FROM seed_db.taxonomy_reference;
        """)
        conn.commit()
        cursor.execute("DETACH DATABASE seed_db;")
        cursor.execute("SELECT count(*) FROM taxonomy_reference;")
        count = cursor.fetchone()[0]
        conn.close()
        logger.info("Fast seed population loaded %d taxonomy reference records from %s.", count, seed_path)
        return count > 0
    except Exception as e:
        logger.exception("Error during fast seed population: %s", e)
        return False

def fast_backfill_stamps(db_path: str) -> int:
    """Rapidly backfills order and family into stamps table using in-memory dictionary lookup."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT english_name, scientific_name, "order", family FROM taxonomy_reference WHERE "order" != "" OR family != "";')
        rows = cursor.fetchall()
        sci_map = {}
        eng_map = {}
        for eng, sci, o, f in rows:
            if sci:
                sci_map[sci.lower().strip()] = (o, f)
            if eng:
                eng_map[eng.lower().strip()] = (o, f)

        cursor.execute('SELECT id, english_name, scientific_name, "order", family FROM stamps WHERE "order" IS NULL OR "order" = "" OR family IS NULL OR family = "";')
        stamps_to_check = cursor.fetchall()

        updates = []
        for sid, eng, sci, cur_o, cur_f in stamps_to_check:
            sci_l = clean_val(sci).lower()
            eng_l = clean_val(eng).lower()
            hit = None
            if sci_l and sci_l in sci_map:
                hit = sci_map[sci_l]
            elif eng_l and eng_l in eng_map:
                hit = eng_map[eng_l]
            elif sci_l:
                parts = sci_l.split()
                if len(parts) >= 2:
                    two_words = f"{parts[0]} {parts[1]}"
                    if two_words in sci_map:
                        hit = sci_map[two_words]

            if hit:
                new_o = cur_o or hit[0]
                new_f = cur_f or hit[1]
                if new_o != cur_o or new_f != cur_f:
                    updates.append((new_o, new_f, sid))

        if updates:
            logger.info("Fast-backfilling order and family for %d stamps...", len(updates))
            cursor.executemany('UPDATE stamps SET "order" = ?, family = ? WHERE id = ?;', updates)
            conn.commit()
            logger.info("Successfully fast-backfilled %d stamps with order & family.", len(updates))
        return len(updates)
    except Exception as e:
        logger.exception("Error during fast backfill: %s", e)
        conn.rollback()
        return 0
    finally:
        conn.close()

def populate_taxonomy_database(excel_path: Optional[str] = None):
    """
    Populates taxonomy_reference table and backfills stamps with order and family.
    Uses pre-built seed database if available (< 0.1s); falls back to Excel parsing.
    """
    ensure_db_schema()
    db_path = get_database_path()

    # 1. Fast Path: Pre-built SQLite seed database
    seed_path = get_seed_db_path()
    if seed_path and os.path.exists(seed_path):
        logger.info("Found pre-compiled taxonomy seed database at %s. Fast-loading...", seed_path)
        if populate_taxonomy_from_seed(seed_path, db_path):
            updated = fast_backfill_stamps(db_path)
            return {
                "status": "success",
                "source": "seed_db",
                "stamps_updated": updated
            }

    # 2. Fallback Path: Parse Excel file
    if not excel_path:
        excel_path = get_excel_path()

    if not excel_path or not os.path.exists(excel_path):
        logger.warning("Neither seed DB nor taxonomy workbook found. Skipping taxonomy population.")
        return {"status": "skipped", "message": "No seed DB or Excel file found"}

    logger.info("Populating taxonomy database from Excel %s...", excel_path)

    # Dictionary to hold unified taxonomy records keyed by lowercase identifier
    # key: normalized name -> dict
    sci_tax_map: Dict[str, Dict[str, str]] = {}
    eng_tax_map: Dict[str, Dict[str, str]] = {}

    def register_record(eng: str, sci: str, order: str, family: str, group: str = "", genus: str = "", species: str = ""):
        eng = clean_val(eng)
        sci = clean_val(sci)
        order = clean_val(order)
        family = clean_val(family)
        group = clean_val(group)
        genus = clean_val(genus)
        species = clean_val(species)

        if not order and not family:
            return

        rec = {
            "english_name": eng,
            "scientific_name": sci,
            "order": order,
            "family": family,
            "bird_group": group,
            "genus": genus,
            "species": species
        }

        if sci:
            key = sci.lower().strip()
            if key not in sci_tax_map or (not sci_tax_map[key].get("order") and order):
                sci_tax_map[key] = rec

        if eng:
            key = eng.lower().strip()
            if key not in eng_tax_map or (not eng_tax_map[key].get("order") and order):
                eng_tax_map[key] = rec

    # 1. Read IOC 14.1 sheet
    try:
        logger.info("Reading IOC 14.1 sheet...")
        df_ioc = pd.read_excel(excel_path, sheet_name="IOC 14.1")
        df_ioc.columns = [str(c).strip() for c in df_ioc.columns]

        for _, row in df_ioc.iterrows():
            order = row.get("Order")
            family = row.get("Family")
            group = row.get("Group")
            genus = row.get("Genus")
            sp_sci = row.get("Species (Scientific)")
            sp_eng = row.get("Species (English)")
            subsp = row.get("Subspecies")

            clean_g = clean_val(genus)
            clean_sp = clean_val(sp_sci)
            clean_sub = clean_val(subsp).replace("\t", " ").strip()
            clean_eng = clean_val(sp_eng)

            # Binomial e.g. Struthio camelus
            if clean_g and clean_sp:
                binomial = f"{clean_g} {clean_sp.lower()}"
                register_record(clean_eng, binomial, order, family, group, clean_g, clean_sp)

            # Subspecies or scientific trinomial/binomial
            if clean_sub:
                register_record(clean_eng, clean_sub, order, family, group, clean_g, clean_sp)

            # If Species (Scientific) has space (e.g. Archaeopteryx Lithografica)
            if clean_sp and " " in clean_sp:
                register_record(clean_eng, clean_sp, order, family, group, clean_g, "")

            # English name mapping
            if clean_eng:
                register_record(clean_eng, "", order, family, group, clean_g, clean_sp)
    except Exception as e:
        logger.exception("Error processing IOC 14.1 sheet: %s", e)

    # 2. Read Final sheet
    try:
        logger.info("Reading Final sheet...")
        df_final = pd.read_excel(excel_path, sheet_name="Final")
        df_final.columns = [str(c).strip() for c in df_final.columns]

        for _, row in df_final.iterrows():
            order = row.get("Order")
            family = row.get("Family")
            group = row.get("Group")
            genus = row.get("Genus")
            sci = row.get("Scientific name")
            eng = row.get("English name")

            clean_sci = clean_val(sci)
            clean_eng = clean_val(eng)
            clean_g = clean_val(genus)
            if not clean_g and clean_sci:
                parts = clean_sci.split()
                if len(parts) >= 1:
                    clean_g = parts[0]

            clean_sp = ""
            if clean_sci:
                parts = clean_sci.split()
                if len(parts) >= 2:
                    clean_sp = parts[1]

            register_record(clean_eng, clean_sci, order, family, group, clean_g, clean_sp)
    except Exception as e:
        logger.exception("Error processing Final sheet: %s", e)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Re-populate taxonomy_reference table
        cursor.execute("DELETE FROM taxonomy_reference;")
        
        # Collect distinct entries to insert
        all_unique_entries = []
        seen = set()

        # Combine both maps into unified list of taxonomy rows
        combined = list(sci_tax_map.values()) + list(eng_tax_map.values())
        for item in combined:
            key = (
                item["english_name"].lower(),
                item["scientific_name"].lower(),
                item["order"].lower(),
                item["family"].lower()
            )
            if key not in seen and (item["order"] or item["family"]):
                seen.add(key)
                all_unique_entries.append((
                    item["english_name"],
                    item["scientific_name"],
                    item["order"],
                    item["family"],
                    item["bird_group"],
                    item["genus"],
                    item["species"]
                ))

        cursor.executemany("""
            INSERT INTO taxonomy_reference (
                english_name, scientific_name, "order", family, bird_group, genus, species
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, all_unique_entries)
        conn.commit()
        logger.info("Inserted %d taxonomy reference records into taxonomy_reference.", len(all_unique_entries))

        # 3. Backfill order and family into existing stamps in stamps table
        cursor.execute('SELECT id, english_name, scientific_name, "order", family FROM stamps;')
        stamps = cursor.fetchall()

        stamps_to_update = []
        for sid, eng, sci, cur_order, cur_family in stamps:
            # Only update if order or family is currently empty
            if cur_order and cur_family:
                continue

            eng_l = clean_val(eng).lower()
            sci_l = clean_val(sci).lower()

            hit = None
            if sci_l and sci_l in sci_tax_map:
                hit = sci_tax_map[sci_l]
            elif eng_l and eng_l in eng_tax_map:
                hit = eng_tax_map[eng_l]
            elif sci_l:
                parts = sci_l.split()
                if len(parts) >= 2:
                    two_words = f"{parts[0]} {parts[1]}"
                    if two_words in sci_tax_map:
                        hit = sci_tax_map[two_words]

            if hit:
                new_order = cur_order or hit["order"]
                new_family = cur_family or hit["family"]
                stamps_to_update.append((new_order, new_family, sid))

        if stamps_to_update:
            logger.info("Backfilling order and family for %d stamps...", len(stamps_to_update))
            cursor.executemany('UPDATE stamps SET "order" = ?, family = ? WHERE id = ?;', stamps_to_update)
            conn.commit()
            logger.info("Successfully backfilled %d stamps with order & family.", len(stamps_to_update))

    except Exception:
        logger.exception("Failed during database taxonomy population")
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "status": "success",
        "reference_records": len(all_unique_entries),
        "stamps_updated": len(stamps_to_update)
    }

def ensure_taxonomy_populated():
    """Checks if taxonomy_reference has data; if empty, populates it."""
    db_path = get_database_path()
    if not os.path.exists(db_path):
        return

    # Ensure schema and auto-repair any corruption before querying
    ensure_db_schema()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='taxonomy_reference';")
        if not cursor.fetchone()[0]:
            conn.close()
            ensure_db_schema()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

        cursor.execute("SELECT count(*) FROM taxonomy_reference;")
        count = cursor.fetchone()[0]

        cursor.execute('SELECT count(*) FROM stamps WHERE "order" IS NOT NULL AND "order" != \'\';')
        stamps_with_order = cursor.fetchone()[0]
        conn.close()

        if count == 0 or stamps_with_order == 0:
            logger.info("Taxonomy data incomplete (ref_count=%d, stamps_with_order=%d). Initiating population...", count, stamps_with_order)
            populate_taxonomy_database()
    except Exception as e:
        logger.exception("Error checking taxonomy population: %s. Attempting schema repair and retry...", e)
        try:
            ensure_db_schema()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM taxonomy_reference;")
            count = cursor.fetchone()[0]
            cursor.execute('SELECT count(*) FROM stamps WHERE "order" IS NOT NULL AND "order" != \'\';')
            stamps_with_order = cursor.fetchone()[0]
            conn.close()
            if count == 0 or stamps_with_order == 0:
                populate_taxonomy_database()
        except Exception as retry_err:
            logger.exception("Taxonomy population retry after repair also failed: %s", retry_err)

def lookup_taxonomy(db: Session, english_name: Optional[str] = None, scientific_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Looks up bird taxonomy based on English common name or Scientific binomial name.
    Provides two-way resolution:
    - Given scientific_name -> resolves english_name (Common Name) + order, family, etc.
    - Given english_name -> resolves scientific_name + order, family, etc.
    Checks stamps catalog first for established names, then taxonomy_reference.
    """
    clean_eng = clean_val(english_name).strip()
    clean_sci = clean_val(scientific_name).strip()

    if not clean_eng and not clean_sci:
        return None

    # Priority 1: When scientific_name is provided, resolve Common Name and taxonomy
    if clean_sci:
        # Check stamps catalog first (most relevant common names)
        stamp = db.query(models.Stamp).filter(
            func.lower(models.Stamp.scientific_name) == clean_sci.lower(),
            models.Stamp.english_name != "",
            models.Stamp.english_name.isnot(None),
            or_(models.Stamp.order != "", models.Stamp.family != "")
        ).order_by(models.Stamp.my_collection.desc(), models.Stamp.id.asc()).first()
        if stamp and (stamp.order or stamp.family):
            parts = (stamp.scientific_name or clean_sci).split()
            return {
                "english_name": stamp.english_name or clean_eng,
                "scientific_name": stamp.scientific_name or clean_sci,
                "order": stamp.order or "",
                "family": stamp.family or "",
                "bird_group": stamp.bird_group or "",
                "genus": stamp.genus or (parts[0] if len(parts) >= 1 else ""),
                "species": stamp.species or (parts[1] if len(parts) >= 2 else "")
            }

        # Check taxonomy_reference table
        ref = db.query(models.TaxonomyReference).filter(
            func.lower(models.TaxonomyReference.scientific_name) == clean_sci.lower(),
            or_(models.TaxonomyReference.order != "", models.TaxonomyReference.family != "")
        ).order_by(models.TaxonomyReference.id.desc()).first()
        if ref and (ref.order or ref.family):
            parts = (ref.scientific_name or clean_sci).split()
            return {
                "english_name": ref.english_name or clean_eng,
                "scientific_name": ref.scientific_name or clean_sci,
                "order": ref.order or "",
                "family": ref.family or "",
                "bird_group": ref.bird_group or "",
                "genus": ref.genus or (parts[0] if len(parts) >= 1 else ""),
                "species": ref.species or (parts[1] if len(parts) >= 2 else "")
            }

        # Try binomial match (first two words) if user typed trinomial / subspecies
        parts = clean_sci.split()
        if len(parts) >= 2:
            binomial = f"{parts[0]} {parts[1]}".lower()
            stamp_bi = db.query(models.Stamp).filter(
                func.lower(models.Stamp.scientific_name) == binomial,
                models.Stamp.english_name != "",
                models.Stamp.english_name.isnot(None),
                or_(models.Stamp.order != "", models.Stamp.family != "")
            ).order_by(models.Stamp.my_collection.desc(), models.Stamp.id.asc()).first()
            if stamp_bi and (stamp_bi.order or stamp_bi.family):
                return {
                    "english_name": stamp_bi.english_name or clean_eng,
                    "scientific_name": stamp_bi.scientific_name or clean_sci,
                    "order": stamp_bi.order or "",
                    "family": stamp_bi.family or "",
                    "bird_group": stamp_bi.bird_group or "",
                    "genus": stamp_bi.genus or parts[0],
                    "species": stamp_bi.species or parts[1]
                }

            ref_bi = db.query(models.TaxonomyReference).filter(
                func.lower(models.TaxonomyReference.scientific_name) == binomial,
                or_(models.TaxonomyReference.order != "", models.TaxonomyReference.family != "")
            ).order_by(models.TaxonomyReference.id.desc()).first()
            if ref_bi and (ref_bi.order or ref_bi.family):
                return {
                    "english_name": ref_bi.english_name or clean_eng,
                    "scientific_name": ref_bi.scientific_name or clean_sci,
                    "order": ref_bi.order or "",
                    "family": ref_bi.family or "",
                    "bird_group": ref_bi.bird_group or "",
                    "genus": ref_bi.genus or parts[0],
                    "species": ref_bi.species or parts[1]
                }

    # Priority 2: When english_name is provided, resolve Scientific Name and taxonomy
    if clean_eng:
        # Check stamps catalog first
        stamp = db.query(models.Stamp).filter(
            func.lower(models.Stamp.english_name) == clean_eng.lower(),
            models.Stamp.scientific_name != "",
            models.Stamp.scientific_name.isnot(None),
            or_(models.Stamp.order != "", models.Stamp.family != "")
        ).order_by(models.Stamp.my_collection.desc(), models.Stamp.id.asc()).first()
        if stamp and (stamp.order or stamp.family):
            parts = (stamp.scientific_name or "").split()
            return {
                "english_name": stamp.english_name or clean_eng,
                "scientific_name": stamp.scientific_name or clean_sci,
                "order": stamp.order or "",
                "family": stamp.family or "",
                "bird_group": stamp.bird_group or "",
                "genus": stamp.genus or (parts[0] if len(parts) >= 1 else ""),
                "species": stamp.species or (parts[1] if len(parts) >= 2 else "")
            }

        # Check taxonomy_reference table
        ref = db.query(models.TaxonomyReference).filter(
            func.lower(models.TaxonomyReference.english_name) == clean_eng.lower(),
            or_(models.TaxonomyReference.order != "", models.TaxonomyReference.family != "")
        ).order_by(models.TaxonomyReference.id.desc()).first()
        if ref and (ref.order or ref.family):
            parts = (ref.scientific_name or "").split()
            return {
                "english_name": ref.english_name or clean_eng,
                "scientific_name": ref.scientific_name or clean_sci,
                "order": ref.order or "",
                "family": ref.family or "",
                "bird_group": ref.bird_group or "",
                "genus": ref.genus or (parts[0] if len(parts) >= 1 else ""),
                "species": ref.species or (parts[1] if len(parts) >= 2 else "")
            }

    return None

def save_taxonomy(
    db: Session,
    english_name: Optional[str] = "",
    scientific_name: Optional[str] = "",
    order: Optional[str] = "",
    family: Optional[str] = "",
    bird_group: Optional[str] = "",
    genus: Optional[str] = "",
    species: Optional[str] = ""
) -> Optional[models.TaxonomyReference]:
    """
    Saves or updates bird taxonomy into the local taxonomy_reference table.
    Ensures that user-entered order and family information is remembered for future autofills.
    """
    clean_eng = clean_val(english_name)
    clean_sci = clean_val(scientific_name)
    clean_order = clean_val(order)
    clean_family = clean_val(family)
    clean_group = clean_val(bird_group)
    clean_genus = clean_val(genus)
    clean_species = clean_val(species)

    if not clean_order and not clean_family:
        return None

    if not clean_eng and not clean_sci:
        return None

    # Derive genus / species if missing and scientific name has >= 2 words
    if clean_sci and (not clean_genus or not clean_species):
        parts = clean_sci.split()
        if not clean_genus and len(parts) >= 1:
            clean_genus = parts[0]
        if not clean_species and len(parts) >= 2:
            clean_species = parts[1]

    # Check for existing record
    existing = None
    if clean_sci:
        existing = db.query(models.TaxonomyReference).filter(
            func.lower(models.TaxonomyReference.scientific_name) == clean_sci.lower()
        ).first()

    if not existing and clean_eng:
        existing = db.query(models.TaxonomyReference).filter(
            func.lower(models.TaxonomyReference.english_name) == clean_eng.lower()
        ).first()

    if existing:
        if clean_order:
            existing.order = clean_order
        if clean_family:
            existing.family = clean_family
        if clean_eng and not existing.english_name:
            existing.english_name = clean_eng
        if clean_sci and not existing.scientific_name:
            existing.scientific_name = clean_sci
        if clean_group and not existing.bird_group:
            existing.bird_group = clean_group
        if clean_genus and not existing.genus:
            existing.genus = clean_genus
        if clean_species and not existing.species:
            existing.species = clean_species
        db.commit()
        db.refresh(existing)
        return existing
    else:
        new_entry = models.TaxonomyReference(
            english_name=clean_eng,
            scientific_name=clean_sci,
            order=clean_order,
            family=clean_family,
            bird_group=clean_group,
            genus=clean_genus,
            species=clean_species
        )
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)
        return new_entry
