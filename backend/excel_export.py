import os
import sys
import datetime
import logging
import pandas as pd
from sqlalchemy.orm import Session
import models

logger = logging.getLogger(__name__)

def get_export_dir() -> str:
    """
    Returns the absolute path to the 'my collection sheets' directory,
    located in the application directory (next to executable in frozen mode,
    or next to project root in development mode). In frozen mode, falls back
    to Documents\\BirdStamp\\my collection sheets if the exe directory isn't writable.
    """
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        export_dir = os.path.join(exe_dir, "my collection sheets")
        try:
            os.makedirs(export_dir, exist_ok=True)
            test_file = os.path.join(export_dir, ".write_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            return export_dir
        except Exception:
            logger.warning("Export dir '%s' not writable, falling back to Documents", export_dir, exc_info=True)
            fallback_dir = os.path.join(os.path.expanduser("~"), "Documents", "BirdStamp", "my collection sheets")
            os.makedirs(fallback_dir, exist_ok=True)
            return fallback_dir
    else:
        # Development mode: place folder in the workspace root (parent of backend)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        export_dir = os.path.join(base_dir, "my collection sheets")
        os.makedirs(export_dir, exist_ok=True)
        return export_dir

def export_collection_to_excel(db: Session) -> dict:
    """
    Exports all stamps from SQLite database into an Excel spreadsheet (.xlsx)
    and saves it inside the 'my collection sheets' folder.
    """
    try:
        export_dir = get_export_dir()
        
        # 1. Fetch all stamps from DB
        stamps = db.query(models.Stamp).all()
        
        # 2. Define standard columns matching models and collection metadata
        columns = [
            'ID', 'Country', 'Year', 'Face Value', 'English Name', 'Scientific Name',
            'Bird Group', 'Genus', 'Species', 'Category', 'Type', 'Release Date',
            'Image URL', 'My Collection', 'Condition', 'Duplicate', 'Error',
            'Description', 'Element Group', 'Element', 'Element Description'
        ]
        
        data = []
        for s in stamps:
            my_col_str = "Yes" if s.my_collection else ""
            
            row = {
                'ID': s.id,
                'Country': s.country or "",
                'Year': s.year or "",
                'Face Value': s.face_value or "",
                'English Name': s.english_name or "",
                'Scientific Name': s.scientific_name or "",
                'Bird Group': s.bird_group or "",
                'Genus': s.genus or "",
                'Species': s.species or "",
                'Category': s.category or "",
                'Type': s.stamp_type or "",
                'Release Date': s.release_date or "",
                'Image URL': s.image_url or "",
                'My Collection': my_col_str,
                'Condition': s.condition or "",
                'Duplicate': s.duplicate or "no",
                'Error': s.error or "",
                'Description': s.description or "",
                'Element Group': s.element_group or "",
                'Element': s.element or "",
                'Element Description': s.element_description or ""
            }
            data.append(row)
            
        df = pd.DataFrame(data, columns=columns)
        
        # 3. Save as timestamped file and main export file
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamped_filename = f"My Collection_Export_{timestamp_str}.xlsx"
        main_filename = "My Collection_Export.xlsx"
        
        main_filepath = os.path.join(export_dir, main_filename)
        timestamped_filepath = os.path.join(export_dir, timestamped_filename)
        
        # Write both files using openpyxl engine
        with pd.ExcelWriter(main_filepath, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
            
        with pd.ExcelWriter(timestamped_filepath, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
            
        return {
            "status": "success",
            "message": f"Successfully exported {len(stamps)} stamps to 'my collection sheets'",
            "folder": export_dir,
            "filename": main_filename,
            "timestamped_filename": timestamped_filename,
            "file_path": main_filepath,
            "total_stamps": len(stamps)
        }
        
    except Exception:
        logger.exception("Excel Export failed")
        raise
