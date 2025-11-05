from dataclasses import dataclass, field
from typing import List, Optional
from .base import BlockType
from .version import Version


@dataclass
class Block:
    id: str
    type: BlockType
    title: Optional[str]
    versions: List[Version]
