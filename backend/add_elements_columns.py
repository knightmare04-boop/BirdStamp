import sqlite3

db_path = 'bird_stamps.db'

def add_columns():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE stamps ADD COLUMN element_group VARCHAR DEFAULT ''")
        print("Added element_group column")
    except sqlite3.OperationalError as e:
        print(f"element_group column might already exist: {e}")

    try:
        cursor.execute("ALTER TABLE stamps ADD COLUMN element VARCHAR DEFAULT ''")
        print("Added element column")
    except sqlite3.OperationalError as e:
        print(f"element column might already exist: {e}")
        
    try:
        cursor.execute("ALTER TABLE stamps ADD COLUMN element_description VARCHAR DEFAULT ''")
        print("Added element_description column")
    except sqlite3.OperationalError as e:
        print(f"element_description column might already exist: {e}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    add_columns()
