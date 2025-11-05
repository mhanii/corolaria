from dataclasses import dataclass, field
from typing import List, Optional, Union
from .base import ReferenciaType
from src.domain.value_objects.relaciones_anteriores_model import RelacionesAnteriores
from src.domain.value_objects.relaciones_posteriores_model import RelacionesPosteriores







@dataclass
class Referencia:
    id_norma: str
    type: ReferenciaType
    relacion: int
    text: str

    def get_code(self) -> int:
        """Get the code of the relacion posterior."""
        return self.id
    def get_name(self) -> Optional[str]:
        """Get the name of the relacion using the RelacionesPosteriores or RelacionesAnteriores model."""
        if self.type == ReferenciaType.ANTERIOR:
            return RelacionesAnteriores.name_from_code(self.id)
        else:
            return RelacionesPosteriores.name_from_code(self.id)

    def is_valid(self) -> bool:
        """Check if the relacion posterior ID is valid."""
        return self.get_name() is not None
