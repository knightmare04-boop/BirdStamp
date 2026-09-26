import pandas as pd
import sqlite3

conn = sqlite3.connect('bird_stamps.db')
c = conn.cursor()
import os
excel_candidates = ['../data/collections/My Collection_Final List_1.1.xlsx', '../My Collection_Final List_1.1.xlsx']
excel_path = next((p for p in excel_candidates if os.path.exists(p)), excel_candidates[0])
df = pd.read_excel(excel_path)
df.columns = [str(col).strip() for col in df.columns]

owned = df[df['My Collection'].notna()]
print(f"Total owned in excel: {len(owned)}")

# Get all owned stamps currently in DB
c.execute("SELECT country, english_name, scientific_name, face_value FROM stamps WHERE my_collection=1")
db_owned = c.fetchall()

missing = []

for idx, row in owned.iterrows():
    country = str(row.get('Country', '')).strip()
    sci_name = str(row.get('Scientific name', '')).strip()
    eng_name = str(row.get('English name', '')).strip()
    face_val = str(row.get('Face value', '')).strip()
    year = str(row.get('Year', '')).strip()
    
    # Simple check if this combination exists in db_owned
    # Actually, sync.py doesn't track which excel row matched which DB row.
    # Let's run the exact sync.py logic:
    
    stamp = None
    c.execute("SELECT english_name, scientific_name, face_value, year FROM stamps WHERE country=? AND scientific_name=?", (country, sci_name))
    res = c.fetchone()
    if res and sci_name != 'nan':
        stamp = res
    if not stamp and eng_name != 'nan':
        c.execute("SELECT english_name, scientific_name, face_value, year FROM stamps WHERE country=? AND english_name=?", (country, eng_name))
        res = c.fetchone()
        if res: stamp = res
    if not stamp and face_val != 'nan':
        # we will just do face value
        c.execute("SELECT english_name, scientific_name, face_value, year FROM stamps WHERE country=? AND face_value=?", (country, face_val))
        res = c.fetchone()
        if res: stamp = res

    if not stamp:
        missing.append((country, eng_name, sci_name, face_val, year))

print(f"Missing count: {len(missing)}")
for m in missing[:5]:
    print(f"MISSING: Country='{m[0]}' Eng='{m[1]}' Sci='{m[2]}' Face='{m[3]}' Year='{m[4]}'")
    # Let's print what is actually in the DB for that country!
    c.execute("SELECT english_name, scientific_name, face_value, year FROM stamps WHERE country=? LIMIT 3", (m[0],))
    print("  DB HAS:", c.fetchall())

