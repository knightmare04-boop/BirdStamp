from pydantic import BaseModel, ConfigDict
from typing import Optional

class StampBase(BaseModel):
    country: Optional[str] = None
    year: Optional[str] = None
    scott_num: Optional[str] = None
    stanley_gibbons: Optional[str] = None
    yvert_tellier: Optional[str] = None
    face_value: Optional[str] = None
    english_name: Optional[str] = None
    scientific_name: Optional[str] = None
    category: Optional[str] = None
    stamp_type: Optional[str] = None
    release_date: Optional[str] = None
    image_url: Optional[str] = None
    bird_group: Optional[str] = ""
    genus: Optional[str] = ""
    species: Optional[str] = ""
    my_collection: Optional[bool] = False
    condition: Optional[str] = ""
    duplicate: Optional[str] = "no"
    error: Optional[str] = ""
    description: Optional[str] = ""
    element_group: Optional[str] = ""
    element: Optional[str] = ""
    element_description: Optional[str] = ""

class StampCreate(StampBase):
    pass

class StampUpdate(BaseModel):
    my_collection: Optional[bool] = None
    condition: Optional[str] = None
    duplicate: Optional[str] = None
    error: Optional[str] = None
    description: Optional[str] = None
    element_group: Optional[str] = None
    element: Optional[str] = None
    element_description: Optional[str] = None
    bird_group: Optional[str] = None
    genus: Optional[str] = None
    species: Optional[str] = None

class Stamp(StampBase):
    id: int
    bird_group: str = ""
    genus: str = ""
    species: str = ""
    my_collection: bool
    duplicate: str
    error: str
    description: str
    element_group: str
    element: str
    element_description: str

    model_config = ConfigDict(from_attributes=True)

from typing import Generic, TypeVar, List, Dict
T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    limit: int

class PhilatelicOptions(BaseModel):
    conditions: List[str]
    element_groups: List[str]
    elements_by_group: Dict[str, List[str]]
    all_elements: List[str]
    element_descriptions: Dict[str, str]
