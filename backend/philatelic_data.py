import os
import sys
import logging
import pandas as pd

logger = logging.getLogger(__name__)

_cached_options = None

def get_philatelic_options():
    global _cached_options
    if _cached_options is not None:
        return _cached_options
    
    # Defaults
    default_conditions = [
        "Mint Never Hinged (MNH)",
        "Mint Hinged (MH)",
        "Mint Without Gum",
        "Specimen Overprints",
        "Imperforate Varieties",
        "Color Varieties",
        "Used",
        "First Day Cover (FDC)",
        "Cancelled to Order (CTO)",
        "On Cover / Postal History"
    ]
    
    default_element_groups = [
        "Design & Production",
        "Issued Stamps",
        "Postal Stationery",
        "Postal History",
        "Specialized Items",
        "Elements to Avoid"
    ]
    
    element_groups = []
    elements_by_group = {}
    all_elements = []
    element_descriptions = {}
    conditions = []
    
    # Try finding Philatelic Elements.xlsx
    this_file = os.path.abspath(__file__)
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(sys._MEIPASS, 'Philatelic Elements.xlsx'),
            os.path.join(exe_dir, 'Philatelic Elements.xlsx'),
            os.path.join(exe_dir, 'data', 'elements', 'Philatelic Elements.xlsx'),
        ]
    else:
        project_dir = os.path.dirname(os.path.dirname(this_file))
        backend_dir = os.path.dirname(this_file)
        candidates = [
            os.path.join(project_dir, 'data', 'elements', 'Philatelic Elements.xlsx'),
            os.path.join(project_dir, 'Philatelic Elements.xlsx'),
            os.path.join(backend_dir, 'data', 'elements', 'Philatelic Elements.xlsx'),
            os.path.join(backend_dir, 'Philatelic Elements.xlsx'),
        ]
    
    found_path = None
    for p in candidates:
        if os.path.exists(p):
            found_path = p
            break
            
    if found_path:
        try:
            # Sheet 1: Elements
            df_s1 = pd.read_excel(found_path, sheet_name='Sheet1')
            for _, row in df_s1.iterrows():
                eg = str(row.get('Element Group', '')).strip()
                elem = str(row.get('Elements', '')).strip()
                desc = str(row.get('Description', '')).strip()
                
                if eg == 'nan': eg = ''
                if elem == 'nan': elem = ''
                if desc == 'nan': desc = ''
                
                # Clean up formatting
                elem = elem.rstrip('.')
                
                if eg and eg not in element_groups:
                    element_groups.append(eg)
                    
                if eg not in elements_by_group:
                    elements_by_group[eg] = []
                    
                if elem:
                    if elem not in elements_by_group[eg]:
                        elements_by_group[eg].append(elem)
                    if elem not in all_elements:
                        all_elements.append(elem)
                    if desc:
                        element_descriptions[elem] = desc
                        
            # Sheet 2: Condition
            df_s2 = pd.read_excel(found_path, sheet_name='Sheet2')
            for col in df_s2.columns:
                for val in df_s2[col].dropna():
                    sval = str(val).strip()
                    if sval and sval not in conditions and len(sval) < 60 and not sval.startswith('Stamps'):
                        # Normalize case
                        if sval not in conditions:
                            conditions.append(sval)
        except Exception:
            logger.exception("Error reading Philatelic Elements.xlsx")

    # Fallbacks if sheet was incomplete or missing
    if not conditions:
        conditions = default_conditions
    else:
        # Ensure common items are present
        for c in ["Used", "First Day Cover (FDC)"]:
            if c not in conditions:
                conditions.append(c)
                
    if not element_groups:
        element_groups = default_element_groups

    _cached_options = {
        "conditions": conditions,
        "element_groups": element_groups,
        "elements_by_group": elements_by_group,
        "all_elements": all_elements,
        "element_descriptions": element_descriptions
    }
    return _cached_options
