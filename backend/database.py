from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import sys
import os
import shutil
import sqlite3
import logging

logger = logging.getLogger(__name__)

def get_database_path():
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        local_db = os.path.join(exe_dir, "bird_stamps.db")
        
        # Test if exe directory is writable
        is_writable = False
        try:
            test_file = os.path.join(exe_dir, ".write_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            is_writable = True
        except Exception:
            is_writable = False
            
        if is_writable:
            return local_db
        else:
            # Fallback to LocalAppData for restricted folders (e.g., Program Files)
            app_data_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "BirdStamp")
            os.makedirs(app_data_dir, exist_ok=True)
            app_data_db = os.path.join(app_data_dir, "bird_stamps.db")
            
            # If DB doesn't exist in AppData but exists in bundle, copy it over
            if not os.path.exists(app_data_db) and os.path.exists(local_db):
                try:
                    shutil.copy2(local_db, app_data_db)
                except Exception:
                    logger.exception("Error copying DB to AppData")
                    
            return app_data_db
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "bird_stamps.db")

def get_uploads_dir() -> str:
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        local_uploads = os.path.join(exe_dir, "uploads")
        
        is_writable = False
        try:
            os.makedirs(local_uploads, exist_ok=True)
            test_file = os.path.join(local_uploads, ".write_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            is_writable = True
        except Exception:
            is_writable = False
            
        if is_writable:
            return local_uploads
        else:
            app_data_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "BirdStamp")
            uploads_dir = os.path.join(app_data_dir, "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            return uploads_dir
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        uploads_dir = os.path.join(base_dir, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        return uploads_dir

db_path = get_database_path()
SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30}
)

# Enable WAL mode for high-concurrency SQLite operations
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_db_schema():
    """Ensure all required columns exist in the SQLite database."""
    if not os.path.exists(db_path):
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(stamps)")
        columns = [row[1] for row in cursor.fetchall()]
        
        required_columns = {
            "bird_group": "VARCHAR DEFAULT ''",
            "genus": "VARCHAR DEFAULT ''",
            "species": "VARCHAR DEFAULT ''",
            "element_group": "VARCHAR DEFAULT ''",
            "element": "VARCHAR DEFAULT ''",
            "element_description": "VARCHAR DEFAULT ''",
            "description": "VARCHAR DEFAULT ''",
            "error": "VARCHAR DEFAULT ''",
            "duplicate": "VARCHAR DEFAULT 'no'",
            "condition": "VARCHAR DEFAULT ''",
            "my_collection": "BOOLEAN DEFAULT 0"
        }
        
        for col_name, col_type in required_columns.items():
            if col_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE stamps ADD COLUMN {col_name} {col_type}")
                    logger.info("Added missing column '%s' to stamps table.", col_name)
                except Exception:
                    logger.exception("Error adding column '%s'", col_name)

        conn.commit()
    except Exception:
        logger.exception("Schema check error")
    finally:
        conn.close()
