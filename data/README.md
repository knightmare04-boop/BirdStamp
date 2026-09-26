# Bird Stamp Collection — Data Directory Guide

This directory contains reference datasets, collection source spreadsheets, and philatelic classification taxonomies used by the Bird Stamp Collection application.

---

## Directory Structure & Categories

```
data/
├── collections/
│   └── My Collection_Final List_1.1.xlsx     # Master collection spreadsheet & IOC 14.1 data
├── elements/
│   ├── Philatelic Elements.xlsx              # Philatelic classification hierarchy & groups
│   └── My collection element link.xlsx       # Condition-to-element mapping table
└── ioc_reference/
    ├── master_ioc_list_v15.2.xlsx            # IOC World Bird List (v15.2) full taxonomy
    └── Multiling IOC 15.2.xlsx               # Multilingual bird species names dataset
```

---

## Folder Descriptions

### 1. `collections/`
- **`My Collection_Final List_1.1.xlsx`**:
  - The primary source dataset containing bird stamp records, countries, face values, years, English names, scientific names, descriptions, and user collection statuses.
  - Contains sheet **`IOC 14.1`** used by the synchronization and IOC data matching scripts (`apply_ioc_data.py`, `sync.py`).

### 2. `elements/`
- **`Philatelic Elements.xlsx`**:
  - Defines the standardized philatelic element categories and descriptions (e.g., *Design & Production*, *Issued Stamps*, *Postal Stationery*, *Postal History*, *Specialized Items*).
  - Loaded dynamically by the application backend (`philatelic_data.py`) to populate dropdown menus and element badges in the UI.
- **`My collection element link.xlsx`**:
  - Contains relation tables mapping collection conditions to philatelic elements and classification rules.

### 3. `ioc_reference/`
- **`master_ioc_list_v15.2.xlsx`**:
  - The official International Ornithologists' Union (IOC) World Bird List version 15.2 master classification file (Orders, Families, Genera, Species, Authorities, and English names).
- **`Multiling IOC 15.2.xlsx`**:
  - Multilingual translations for IOC 15.2 bird species names across multiple languages (French, German, Spanish, etc.).
