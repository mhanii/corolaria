from dataclasses import dataclass
from typing import Optional

from .base import ElementType

from enum import Enum
import hashlib



@dataclass
class Element:
    """Base class for document elements."""
    element_type: ElementType
    content: Optional[str] = None

    def get_type(self) -> ElementType:
        """Get the type of the element."""
        return self.element_type

