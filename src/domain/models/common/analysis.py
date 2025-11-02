from dataclasses import dataclass
from typing import List
from .base import Materia
from .referencia import Referencia


@dataclass
class Analysis:
    materias: List[Materia]  
    referencias_anteriores: List[Referencia]  # Using RelacionesAnteriores model
    referencias_posteriores: List[Referencia]  # Using RelacionesPosteriores model


