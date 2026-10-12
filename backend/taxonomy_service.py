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

def populate_taxonomy_database(excel_path: Optional[str] = None):
    """
    Parses IOC 14.1 and Final sheets from My Collection_Final List_1.1.xlsx,
    populates the taxonomy_reference table in SQLite, and backfills order and family
    for all existing stamps in bird_stamps.db.
    """
    if not excel_path:
        excel_path = get_excel_path()

    if not excel_path or not os.path.exists(excel_path):
        logger.warning("Taxonomy workbook not found at %s. Skipping taxonomy population.", excel_path)
        return {"status": "skipped", "message": "Excel file not found"}

    logger.info("Populating taxonomy database from %s...", excel_path)
    ensure_db_schema()
    db_path = get_database_path()

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
        logger.exception("Error checking taxonomy population: %s", e)

def lookup_taxonomy(db: Session, english_name: Optional[str] = None, scientific_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Looks up bird taxonomy based on English common name or Scientific binomial name.
    Checks taxonomy_reference first, then stamps table as fallback.
    Returns dictionary with order, family, bird_group, genus, species, or None.
    """
    clean_eng = clean_val(english_name).strip()
    clean_sci = clean_val(scientific_name).strip()

    if not clean_eng and not clean_sci:
        return None

    # 1. Exact match by scientific name in taxonomy_reference
    if clean_sci:
        ref = db.query(models.TaxonomyReference).filter(
            func.lower(models.TaxonomyReference.scientific_name) == clean_sci.lower()
        ).first()
        if ref and (ref.order or ref.family):
            return {
                "order": ref.order or "",
                "family": ref.family or "",
                "bird_group": ref.bird_group or "",
                "genus": ref.genus or "",
                "species": ref.species or ""
            }

        # Try binomial match (first two words)
        parts = clean_sci.split()
        if len(parts) >= 2:
            binomial = f"{parts[0]} {parts[1]}".lower()
            ref = db.query(models.TaxonomyReference).filter(
                func.lower(models.TaxonomyReference.scientific_name) == binomial
            ).first()
            if ref and (ref.order or ref.family):
                return {
                    "order": ref.order or "",
                    "family": ref.family or "",
                    "bird_group": ref.bird_group or "",
                    "genus": ref.genus or parts[0],
                    "species": ref.species or parts[1]
                }

    # 2. Match by English common name in taxonomy_reference
    if clean_eng:
        ref = db.query(models.TaxonomyReference).filter(
            func.lower(models.TaxonomyReference.english_name) == clean_eng.lower()
        ).first()
        if ref and (ref.order or ref.family):
            return {
                "order": ref.order or "",
                "family": ref.family or "",
                "bird_group": ref.bird_group or "",
                "genus": ref.genus or "",
                "species": ref.species or ""
            }

    # 3. Fallback: Search stamps table for existing specimen with matching name
    if clean_sci:
        stamp = db.query(models.Stamp).filter(
            func.lower(models.Stamp.scientific_name) == clean_sci.lower(),
            or_(models.Stamp.order != "", models.Stamp.family != "")
        ).first()
        if stamp and (stamp.order or stamp.family):
            return {
                "order": stamp.order or "",
                "family": stamp.family or "",
                "bird_group": stamp.bird_group or "",
                "genus": stamp.genus or "",
                "species": stamp.species or ""
            }

    if clean_eng:
        stamp = db.query(models.Stamp).filter(
            func.lower(models.Stamp.english_name) == clean_eng.lower(),
            or_(models.Stamp.order != "", models.Stamp.family != "")
        ).first()
        if stamp and (stamp.order or stamp.family):
            return {
                "order": stamp.order or "",
                "family": stamp.family or "",
                "bird_group": stamp.bird_group or "",
                "genus": stamp.genus or "",
                "species": stamp.species or ""
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
