from sqlalchemy import Column, Integer, String, Boolean, Float
from database import Base

class Stamp(Base):
    __tablename__ = "stamps"

    id = Column(Integer, primary_key=True, index=True)
    country = Column(String, index=True)
    year = Column(String, index=True)
    face_value = Column(String)
    english_name = Column(String, index=True)
    scientific_name = Column(String, index=True)
    category = Column(String)
    stamp_type = Column(String)
    release_date = Column(String)
    image_url = Column(String)
    
    # Bird Taxonomy Data
    order = Column("order", String, default="", index=True)
    family = Column(String, default="", index=True)
    bird_group = Column(String, default="", index=True)
    genus = Column(String, default="", index=True)
    species = Column(String, default="", index=True)
    
    # User's Collection Data
    my_collection = Column(Boolean, default=False)
    condition = Column(String, default="")
    duplicate = Column(String, default="no")
    error = Column(String, default="")
    description = Column(String, default="")
    element_group = Column(String, default="")
    element = Column(String, default="")
    element_description = Column(String, default="")

class TaxonomyReference(Base):
    __tablename__ = "taxonomy_reference"

    id = Column(Integer, primary_key=True, index=True)
    english_name = Column(String, default="", index=True)
    scientific_name = Column(String, default="", index=True)
    order = Column("order", String, default="")
    family = Column(String, default="")
    bird_group = Column(String, default="")
    genus = Column(String, default="")
    species = Column(String, default="")

