from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import sys
import os
import shutil
import sqlite3
import logging
import time

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

def repair_database_if_corrupted(db_file: str):
    """Automatically detect and repair database corruption (e.g. from abnormal terminations)."""
    if not os.path.exists(db_file):
        return
    try:
        conn = sqlite3.connect(db_file, timeout=5)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check(1);")
        res = cur.fetchone()
        if res and res[0] == "ok":
            conn.close()
            return
        
        logger.warning("Database integrity check failed: %s. Attempting auto-repair...", res)
        # Attempt 1: Checkpoint WAL and REINDEX
        try:
            cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            cur.execute("REINDEX;")
            conn.commit()
            cur.execute("PRAGMA integrity_check(1);")
            res2 = cur.fetchone()
            if res2 and res2[0] == "ok":
                conn.close()
                logger.info("Database successfully repaired via REINDEX.")
                return
        except Exception:
            pass
        conn.close()

        # Attempt 2: Auto-salvage valid records into clean database
        logger.warning("REINDEX did not resolve corruption. Rebuilding database via salvage dump...")
        bak_file = db_file + f".corrupt_{int(time.time())}.bak"
        try:
            shutil.copy2(db_file, bak_file)
        except Exception:
            pass

        repaired_tmp = db_file + ".repaired.tmp"
        if os.path.exists(repaired_tmp):
            try: os.remove(repaired_tmp)
            except Exception: pass

        src_conn = sqlite3.connect(db_file)
        dst_conn = sqlite3.connect(repaired_tmp)
        dump_success = False
        try:
            for line in src_conn.iterdump():
                try:
                    dst_conn.execute(line)
                except Exception:
                    pass
            dst_conn.commit()
            dump_success = True
        except Exception as dump_err:
            logger.warning("iterdump encountered error: %s. Attempting table-level salvage...", dump_err)

        if not dump_success:
            try:
                cur_src = src_conn.cursor()
                cur_dst = dst_conn.cursor()
                tables = [r[0] for r in cur_src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';").fetchall()]
                for tbl in tables:
                    sql_row = cur_src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (tbl,)).fetchone()
                    if sql_row and sql_row[0]:
                        try:
                            cur_dst.execute(sql_row[0])
                        except Exception:
                            pass
                    try:
                        rows = cur_src.execute(f'SELECT * FROM "{tbl}"').fetchall()
                        if rows:
                            qmarks = ",".join(["?"] * len(rows[0]))
                            cur_dst.executemany(f'INSERT OR IGNORE INTO "{tbl}" VALUES ({qmarks})', rows)
                    except Exception as tbl_err:
                        logger.warning("Could not salvage rows from table %s: %s", tbl, tbl_err)
                dst_conn.commit()
            except Exception as salvage_err:
                logger.exception("Table-level salvage failed: %s", salvage_err)

        dst_conn.close()
        src_conn.close()

        for ext in ["-wal", "-shm", "-journal"]:
            f = db_file + ext
            if os.path.exists(f):
                try: os.remove(f)
                except Exception: pass

        if os.path.exists(repaired_tmp) and os.path.getsize(repaired_tmp) > 1024:
            # Verify repaired database has stamps before replacing
            try:
                check_conn = sqlite3.connect(repaired_tmp)
                stamps_count = check_conn.execute("SELECT count(*) FROM stamps;").fetchone()[0]
                check_conn.close()
                if stamps_count > 0:
                    shutil.move(repaired_tmp, db_file)
                    logger.info("Database successfully salvaged (%d stamps preserved) and replaced.", stamps_count)
                else:
                    logger.warning("Salvaged database contained 0 stamps; leaving original in place.")
            except Exception as ver_err:
                logger.warning("Verification of repaired database failed: %s", ver_err)
    except Exception as e:
        logger.exception("Failed during database repair: %s", e)

def ensure_db_schema():
    """Ensure all required columns exist in the SQLite database."""
    if not os.path.exists(db_path):
        return
    
    repair_database_if_corrupted(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(stamps)")
        columns = [row[1] for row in cursor.fetchall()]
        
        required_columns = {
            "order": "VARCHAR DEFAULT ''",
            "family": "VARCHAR DEFAULT ''",
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
                    cursor.execute(f'ALTER TABLE stamps ADD COLUMN "{col_name}" {col_type}')
                    logger.info("Added missing column '%s' to stamps table.", col_name)
                except Exception:
                    logger.exception("Error adding column '%s'", col_name)

        # Ensure taxonomy_reference table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS taxonomy_reference (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                english_name VARCHAR DEFAULT '',
                scientific_name VARCHAR DEFAULT '',
                "order" VARCHAR DEFAULT '',
                family VARCHAR DEFAULT '',
                bird_group VARCHAR DEFAULT '',
                genus VARCHAR DEFAULT '',
                species VARCHAR DEFAULT ''
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_taxref_eng ON taxonomy_reference (english_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_taxref_sci ON taxonomy_reference (scientific_name);")

        conn.commit()
    except Exception:
        logger.exception("Schema check error")
    finally:
        conn.close()
