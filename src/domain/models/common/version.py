from dataclasses import dataclass, field
from typing import List, Optional, Union
from datetime import datetime
from enum import Enum
import hashlib
from .element import Element
@dataclass
class Version:
    id_norma: str
    fecha_publicacion: datetime
    fecha_vigencia: Optional[datetime]
    content: List[Element]
