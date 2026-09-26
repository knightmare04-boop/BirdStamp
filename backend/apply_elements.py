import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys

# Ensure models are accessible
base_dir = os.path.dirname(__file__)
sys.path.append(base_dir)
from database import Base, engine, SessionLocal
from models import Stamp

def apply_elements():
    # 1. Load the Excel files
    philatelic_candidates = [
        os.path.join(os.path.dirname(base_dir), 'data', 'elements', 'Philatelic Elements.xlsx'),
        os.path.join(os.path.dirname(base_dir), 'Philatelic Elements.xlsx'),
    ]
    philatelic_path = next((p for p in philatelic_candidates if os.path.exists(p)), philatelic_candidates[0])

    link_candidates = [
        os.path.join(os.path.dirname(base_dir), 'data', 'elements', 'My collection element link.xlsx'),
        os.path.join(os.path.dirname(base_dir), 'My collection element link.xlsx'),
    ]
    link_path = next((p for p in link_candidates if os.path.exists(p)), link_candidates[0])
    
    print("Loading Philatelic Elements.xlsx...")
    df_elements = pd.read_excel(philatelic_path)
    
    # Create lookup for Elements -> (Group, Description)
    elements_lookup = {}
    for index, row in df_elements.iterrows():
        element_name = str(row.get('Elements', '')).strip()
        group_name = str(row.get('Element Group', '')).strip()
        desc = str(row.get('Description', '')).strip()
        
        if element_name and element_name != 'nan':
            elements_lookup[element_name.lower()] = {
                'group': group_name if group_name != 'nan' else '',
                'desc': desc if desc != 'nan' else ''
            }
            
    print(f"Loaded {len(elements_lookup)} unique elements.")
    
    print("Loading My collection element link.xlsx...")
    df_links = pd.read_excel(link_path)
    
    # Create lookup for Condition -> New Element
    condition_to_element = {}
    for index, row in df_links.iterrows():
        condition = str(row.get('My Collection', '')).strip()
        new_element = str(row.get('New Element', '')).strip()
        
        if condition and condition != 'nan' and new_element and new_element != 'nan':
            condition_to_element[condition.lower()] = new_element
            
    print(f"Loaded {len(condition_to_element)} condition mappings.")

    # 2. Iterate through database
    db = SessionLocal()
    try:
        stamps = db.query(Stamp).all()
        updated_count = 0
        
        for stamp in stamps:
            # We only really care if they have a condition
            stamp_condition = str(stamp.condition).strip().lower() if stamp.condition else ""
            
            if stamp_condition in condition_to_element:
                new_element = condition_to_element[stamp_condition]
                stamp.element = new_element
                
                # Now lookup the group and description
                lookup_key = new_element.lower()
                if lookup_key in elements_lookup:
                    stamp.element_group = elements_lookup[lookup_key]['group']
                    stamp.element_description = elements_lookup[lookup_key]['desc']
                
                updated_count += 1
                
        db.commit()
        print(f"Successfully updated {updated_count} stamps.")
        
    except Exception as e:
        print(f"Error updating stamps: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    apply_elements()
