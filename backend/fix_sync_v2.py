import pandas as pd
from sqlalchemy.orm import Session
import models
from database import SessionLocal

def run():
    db = SessionLocal()
    # Reset all
    db.query(models.Stamp).update({models.Stamp.my_collection: False, models.Stamp.condition: "", models.Stamp.duplicate: "no", models.Stamp.error: "", models.Stamp.description: ""})
    db.commit()

    excel_candidates = [
        r'..\data\collections\My Collection_Final List_1.1.xlsx',
        r'..\My Collection_Final List_1.1.xlsx'
    ]
    excel_path = next((p for p in excel_candidates if os.path.exists(p)), excel_candidates[0])
    df = pd.read_excel(excel_path)
    df.columns = [str(c).strip() for c in df.columns]
    
    updated_count = 0
    inserted_count = 0
    
    for index, row in df.iterrows():
        my_col_val = row.get('My Collection')
        my_collection = bool(pd.notnull(my_col_val) and str(my_col_val).strip() != "")
        
        if not my_collection:
            continue
            
        country = str(row.get('Country', '')).strip()
        sci_name = str(row.get('Scientific name', '')).strip()
        face_val = str(row.get('Face value', '')).strip()
        eng_name = str(row.get('English name', '')).strip()
        year = str(row.get('Year', '')).strip()
        category = str(row.get('Category', '')).strip()
        stamp_type = str(row.get('Type', '')).strip()
        release_date = str(row.get('Release Date', '')).strip()
            
        condition = str(my_col_val).strip() if pd.notnull(my_col_val) else ""
        
        duplicate_val = row.get('Duplicate')
        duplicate = "no"
        if pd.notnull(duplicate_val):
            if str(duplicate_val).strip().lower() == "yes":
                duplicate = "yes"
            
        error_val = row.get('Error')
        error = str(error_val).strip() if pd.notnull(error_val) else ""
        
        desc_val = row.get('Description')
        description = str(desc_val).strip() if pd.notnull(desc_val) else ""
        
        query = db.query(models.Stamp).filter(models.Stamp.country == country, models.Stamp.my_collection == False)
        stamp = None
        
        # Match logic
        if sci_name and sci_name != 'nan' and face_val and face_val != 'nan':
            stamp = query.filter(models.Stamp.scientific_name == sci_name, models.Stamp.face_value == face_val).first()
        
        if not stamp and eng_name and eng_name != 'nan' and face_val and face_val != 'nan':
            stamp = query.filter(models.Stamp.english_name == eng_name, models.Stamp.face_value == face_val).first()
        
        if not stamp and face_val and face_val != 'nan':
            q = query.filter(models.Stamp.face_value == face_val)
            if year and year != 'nan':
                try:
                    year_f = float(year)
                    year_str = f"{year_f:.2f}"
                    q = q.filter(models.Stamp.year.like(f"%{year_str}%"))
                except ValueError:
                    q = q.filter(models.Stamp.year == year)
            stamp = q.first()
        
        if not stamp and sci_name and sci_name != 'nan':
            stamp = query.filter(models.Stamp.scientific_name == sci_name).first()
            
        if not stamp and eng_name and eng_name != 'nan':
            stamp = query.filter(models.Stamp.english_name == eng_name).first()
            
        if stamp:
            stamp.my_collection = True
            stamp.condition = condition
            stamp.duplicate = duplicate
            stamp.error = error
            stamp.description = description
            db.flush() # Ensure the next query sees this row as my_collection=True
            updated_count += 1
        else:
            # INSERT newly found stamp
            new_stamp = models.Stamp(
                country=country if country != 'nan' else "",
                year=year if year != 'nan' else "",
                face_value=face_val if face_val != 'nan' else "",
                english_name=eng_name if eng_name != 'nan' else "",
                scientific_name=sci_name if sci_name != 'nan' else "",
                category=category if category != 'nan' else "",
                stamp_type=stamp_type if stamp_type != 'nan' else "",
                release_date=release_date if release_date != 'nan' else "",
                image_url="",
                my_collection=True,
                condition=condition,
                duplicate=duplicate,
                error=error,
                description=description
            )
            db.add(new_stamp)
            db.flush()
            inserted_count += 1
            
    db.commit()
    print(f"Updated existing: {updated_count}")
    print(f"Inserted missing: {inserted_count}")
    print(f"Total in collection now: {updated_count + inserted_count}")

if __name__ == '__main__':
    run()
