import pandas as pd
import sqlite3
import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(base_dir)

def populate_ioc_data():
    candidates = [
        os.path.join(project_dir, 'data', 'collections', 'My Collection_Final List_1.1.xlsx'),
        os.path.join(project_dir, 'My Collection_Final List_1.1.xlsx')
    ]
    excel_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
    if not os.path.exists(excel_path):
        print(f"Error: Excel file not found at {excel_path}")
        return

    print("Loading IOC 14.1 sheet...")
    df_ioc = pd.read_excel(excel_path, sheet_name='IOC 14.1')
    df_ioc.columns = [str(c).strip() for c in df_ioc.columns]

    subspecies_lookup = {}
    binomial_lookup = {}
    english_lookup = {}
    scientific_lookup = {}

    for _, row in df_ioc.iterrows():
        group = str(row.get('Group', '')).strip()
        genus = str(row.get('Genus', '')).strip()
        sp_sci = str(row.get('Species (Scientific)', '')).strip()
        sp_eng = str(row.get('Species (English)', '')).strip()
        subsp = str(row.get('Subspecies', '')).strip()
        
        if group == 'nan': group = ''
        if genus == 'nan': genus = ''
        if sp_sci == 'nan': sp_sci = ''
        if sp_eng == 'nan': sp_eng = ''
        if subsp == 'nan': subsp = ''
        
        data = {
            'group': group,
            'genus': genus,
            'species': sp_sci.lower() if sp_sci else '',
            'species_display': sp_sci,
            'species_english': sp_eng,
            'subspecies': subsp
        }
        
        if subsp:
            cleaned_subsp = subsp.replace('\t', '').strip()
            subspecies_lookup[cleaned_subsp.lower()] = data
            
        if genus and sp_sci:
            binomial = f"{genus} {sp_sci}".lower()
            binomial_lookup[binomial] = data
            
        if sp_eng:
            english_lookup[sp_eng.lower()] = data
            
        if sp_sci:
            scientific_lookup[sp_sci.lower()] = data

    print("Loading Final sheet for supplemental taxonomy...")
    df_final = pd.read_excel(excel_path, sheet_name='Final')
    df_final.columns = [str(c).strip() for c in df_final.columns]
    
    final_sci_lookup = {}
    final_eng_lookup = {}
    
    for _, row in df_final.iterrows():
        group = str(row.get('Group', '')).strip()
        genus = str(row.get('Genus', '')).strip()
        sci_name = str(row.get('Scientific name', '')).strip()
        eng_name = str(row.get('English name', '')).strip()
        
        if group == 'nan': group = ''
        if genus == 'nan': genus = ''
        if sci_name == 'nan': sci_name = ''
        if eng_name == 'nan': eng_name = ''
        
        if sci_name:
            parts = sci_name.split()
            sp = parts[1] if len(parts) > 1 else sci_name
            data = {'group': group, 'genus': genus, 'species': sp.lower(), 'species_display': sp}
            final_sci_lookup[sci_name.lower()] = data
        if eng_name:
            parts = sci_name.split() if sci_name else []
            sp = parts[1] if len(parts) > 1 else ''
            data = {'group': group, 'genus': genus, 'species': sp.lower(), 'species_display': sp}
            final_eng_lookup[eng_name.lower()] = data

    db_path = os.path.join(base_dir, 'bird_stamps.db')
    print(f"Connecting to database at {db_path}...")
    
    # Ensure columns exist
    from database import ensure_db_schema
    ensure_db_schema()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, english_name, scientific_name FROM stamps")
    stamps = cursor.fetchall()
    print(f"Updating taxonomy for {len(stamps)} stamps...")

    updated_count = 0
    batch_updates = []

    for sid, eng, sci in stamps:
        sci_l = str(sci).strip().lower() if sci else ''
        eng_l = str(eng).strip().lower() if eng else ''
        
        found = None
        if sci_l in subspecies_lookup:
            found = subspecies_lookup[sci_l]
        elif sci_l in binomial_lookup:
            found = binomial_lookup[sci_l]
        elif eng_l in english_lookup:
            found = english_lookup[eng_l]
        elif sci_l in final_sci_lookup:
            found = final_sci_lookup[sci_l]
        elif eng_l in final_eng_lookup:
            found = final_eng_lookup[eng_l]
        elif sci_l:
            words = sci_l.split()
            if len(words) >= 2:
                two_words = f"{words[0]} {words[1]}"
                if two_words in binomial_lookup:
                    found = binomial_lookup[two_words]
                elif two_words in subspecies_lookup:
                    found = subspecies_lookup[two_words]
                elif two_words in final_sci_lookup:
                    found = final_sci_lookup[two_words]

        if found:
            b_group = found.get('group', '')
            b_genus = found.get('genus', '')
            b_species = found.get('species_display', '') or found.get('species', '')
            
            # If species is empty but scientific name has 2 words, extract second word
            if not b_species and sci:
                parts = str(sci).strip().split()
                if len(parts) >= 2:
                    b_species = parts[1]
                    
            if not b_genus and sci:
                parts = str(sci).strip().split()
                if len(parts) >= 1:
                    b_genus = parts[0]

            batch_updates.append((b_group, b_genus, b_species, sid))
            updated_count += 1
        else:
            # Fallback extraction from scientific name
            b_genus = ""
            b_species = ""
            if sci:
                parts = str(sci).strip().split()
                if len(parts) >= 1:
                    b_genus = parts[0]
                if len(parts) >= 2:
                    b_species = parts[1]
            batch_updates.append(("", b_genus, b_species, sid))

        if len(batch_updates) >= 5000:
            cursor.executemany(
                "UPDATE stamps SET bird_group = ?, genus = ?, species = ? WHERE id = ?",
                batch_updates
            )
            conn.commit()
            batch_updates = []
            print(f"Processed {updated_count} records...")

    if batch_updates:
        cursor.executemany(
            "UPDATE stamps SET bird_group = ?, genus = ?, species = ? WHERE id = ?",
            batch_updates
        )
        conn.commit()

    conn.close()
    print(f"Successfully populated taxonomy for {updated_count} / {len(stamps)} stamps in database.")

if __name__ == '__main__':
    populate_ioc_data()
