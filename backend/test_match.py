import pandas as pd
import sqlite3

conn = sqlite3.connect('bird_stamps.db')
c = conn.cursor()
import os
excel_candidates = ['../data/collections/My Collection_Final List_1.1.xlsx', '../My Collection_Final List_1.1.xlsx']
excel_path = next((p for p in excel_candidates if os.path.exists(p)), excel_candidates[0])
df = pd.read_excel(excel_path)
df.columns = [str(c).strip() for c in df.columns]

owned = df[df['My Collection'].notna()]
print(f"Found {len(owned)} owned stamps in excel")
matches_count = 0

for idx, row in owned.head(20).iterrows():
    country = str(row.get('Country', '')).strip()
    sci_name = str(row.get('Scientific name', '')).strip()
    eng_name = str(row.get('English name', '')).strip()
    face_val = str(row.get('Face value', '')).strip()
    
    # Try exact match on Sci Name
    c.execute('SELECT english_name, scientific_name, face_value FROM stamps WHERE country=? AND scientific_name=?', (country, sci_name))
    matches = c.fetchall()
    
    if len(matches) == 0:
        # Try match on English name
        c.execute('SELECT english_name, scientific_name, face_value FROM stamps WHERE country=? AND english_name=?', (country, eng_name))
        matches = c.fetchall()
    
    if len(matches) == 0:
        # Try match on Face value
        c.execute('SELECT english_name, scientific_name, face_value FROM stamps WHERE country=? AND face_value=?', (country, face_val))
        matches = c.fetchall()

    if len(matches) > 0:
        matches_count += 1
    else:
        print(f"NO MATCH: Country={country}, Eng={eng_name}, Sci={sci_name}, Face={face_val}")

print(f"Total matched out of 20: {matches_count}")
