import pandas as pd
from sqlalchemy.orm import Session
import models
from database import SessionLocal

def main():
    db = SessionLocal()
    excel_candidates = [
        r'..\data\collections\My Collection_Final List_1.1.xlsx',
        r'..\My Collection_Final List_1.1.xlsx'
    ]
    excel_path = next((p for p in excel_candidates if os.path.exists(p)), excel_candidates[0])
    df = pd.read_excel(excel_path)
    df.columns = [str(c).strip() for c in df.columns]
    
    collection_df = df[df['My Collection'].notna() & (df['My Collection'].astype(str).str.strip() != '')]
    print(f"Total in Excel collection: {len(collection_df)}")
    
    found_count = 0
    not_found = []
    
    for index, row in collection_df.iterrows():
        country = str(row.get('Country', '')).strip()
        sci_name = str(row.get('Scientific name', '')).strip()
        face_val = str(row.get('Face value', '')).strip()
        eng_name = str(row.get('English name', '')).strip()
        year = str(row.get('Year', '')).strip()
        
        query = db.query(models.Stamp).filter(models.Stamp.country == country)
        stamp = None
        
        # 1. Exact match: Sci Name + Face Value
        if sci_name and sci_name != 'nan' and face_val and face_val != 'nan':
            stamp = query.filter(models.Stamp.scientific_name == sci_name, models.Stamp.face_value == face_val).first()
        
        # 2. Exact match: English Name + Face Value
        if not stamp and eng_name and eng_name != 'nan' and face_val and face_val != 'nan':
            stamp = query.filter(models.Stamp.english_name == eng_name, models.Stamp.face_value == face_val).first()
            
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
            stamp = q.first()
            
        # 4. Fallback: Sci Name
        if not stamp and sci_name and sci_name != 'nan':
            stamp = query.filter(models.Stamp.scientific_name == sci_name).first()
            
        if stamp:
            found_count += 1
        else:
            not_found.append(row)
            
    print(f"Found in DB: {found_count}")
    print(f"Not found in DB: {len(not_found)}")
    
if __name__ == '__main__':
    main()
