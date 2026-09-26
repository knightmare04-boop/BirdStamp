import logging
import pandas as pd
from sqlalchemy.orm import Session
import models
import math

logger = logging.getLogger(__name__)

sync_state = {"is_running": False, "progress": 0, "total": 0, "message": ""}

def run_sync(excel_path: str, db: Session):
    logger.info("Starting sync from %s...", excel_path)
    sync_state["is_running"] = True
    sync_state["progress"] = 0
    sync_state["message"] = "Loading Excel..."
    try:
        try:
            df = pd.read_excel(excel_path)
        except Exception as e:
            sync_state["message"] = f"Excel read error: {e}"
            logger.exception("Failed to read Excel file")
            return

        # Clean up column names (strip whitespace)
        df.columns = [str(c).strip() for c in df.columns]
        
        updated_count = 0
        not_found_count = 0
        
        sync_state["total"] = len(df)
        
        assigned_db_ids = set()
        
        for index, row in df.iterrows():
            sync_state["progress"] = index + 1
            if index % 100 == 0:
                sync_state["message"] = f"Processed {index} of {len(df)}"
                
            try:
                country = str(row.get('Country', '')).strip()
                year = str(row.get('Year', '')).strip()
                sci_name = str(row.get('Scientific name', '')).strip()
                
                my_col_val = row.get('My Collection')
                my_collection = bool(pd.notnull(my_col_val) and str(my_col_val).strip() != "")
                condition = str(my_col_val).strip() if pd.notnull(my_col_val) else ""
                
                duplicate_val = row.get('Duplicate')
                try:
                    duplicate = str(int(float(duplicate_val))) if pd.notnull(duplicate_val) else "no"
                except (ValueError, TypeError):
                    duplicate = "no"
                
                error_val = row.get('Error')
                error = str(error_val).strip() if pd.notnull(error_val) else ""
                
                desc_val = row.get('Description')
                description = str(desc_val).strip() if pd.notnull(desc_val) else ""
                
                eng_name = str(row.get('English name', '')).strip()
                face_val = str(row.get('Face value', '')).strip()
                
                query = db.query(models.Stamp).filter(models.Stamp.country == country)
                stamp = None
                prototype_stamp = None
                
                def find_match(q):
                    nonlocal stamp, prototype_stamp
                    matches = q.all()
                    for m in matches:
                        if m.id not in assigned_db_ids:
                            stamp = m
                            return True
                        else:
                            if not prototype_stamp:
                                prototype_stamp = m
                    return False
                
                # 1. Exact match: Sci Name + Face Value
                if sci_name and sci_name != 'nan' and face_val and face_val != 'nan':
                    q = query.filter(models.Stamp.scientific_name == sci_name, models.Stamp.face_value == face_val)
                    find_match(q)
                
                # 2. Exact match: English Name + Face Value
                if not stamp and eng_name and eng_name != 'nan' and face_val and face_val != 'nan':
                    q = query.filter(models.Stamp.english_name == eng_name, models.Stamp.face_value == face_val)
                    find_match(q)
                
                # 3. Match: Face Value + Year
                if not stamp and face_val and face_val != 'nan':
                    q = query.filter(models.Stamp.face_value == face_val)
                    if year and year != 'nan':
                        try:
                            year_f = float(year)
                            year_str = f"{year_f:.2f}"
                            q = q.filter(models.Stamp.year.like(f"{year_str}%"))
                        except ValueError:
                            q = q.filter(models.Stamp.year == year)
                    find_match(q)
                
                # 4. Fallback: Sci Name
                if not stamp and sci_name and sci_name != 'nan':
                    q = query.filter(models.Stamp.scientific_name == sci_name)
                    find_match(q)
                
                # 5. Fallback: Eng Name
                if not stamp and eng_name and eng_name != 'nan':
                    q = query.filter(models.Stamp.english_name == eng_name)
                    find_match(q)

                
                if stamp:
                    stamp.my_collection = my_collection
                    stamp.condition = condition
                    stamp.duplicate = duplicate
                    stamp.error = error
                    stamp.description = description
                    db.flush()
                    assigned_db_ids.add(stamp.id)
                    updated_count += 1
                elif prototype_stamp:
                    new_stamp = models.Stamp(
                        country=prototype_stamp.country,
                        year=prototype_stamp.year,
                        face_value=prototype_stamp.face_value,
                        english_name=prototype_stamp.english_name,
                        scientific_name=prototype_stamp.scientific_name,
                        category=prototype_stamp.category,
                        stamp_type=prototype_stamp.stamp_type,
                        release_date=prototype_stamp.release_date,
                        image_url=prototype_stamp.image_url,
                        my_collection=my_collection,
                        condition=condition,
                        duplicate=duplicate,
                        error=error,
                        description=description,
                    )
                    db.add(new_stamp)
                    db.flush()
                    assigned_db_ids.add(new_stamp.id)
                    updated_count += 1
                else:
                    not_found_count += 1
            except Exception:
                logger.exception("Error on row %s", index)
                continue

        try:
            db.commit()
            sync_state["message"] = f"Completed. Updated {updated_count} stamps."
            logger.info("Sync completed. Updated %s stamps. %s not found.", updated_count, not_found_count)
        except Exception as db_e:
            db.rollback()
            sync_state["message"] = f"Database commit error: {db_e}"
            logger.exception("Sync database commit failed")
            
    finally:
        sync_state["is_running"] = False
