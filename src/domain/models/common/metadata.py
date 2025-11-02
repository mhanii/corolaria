from dataclasses import dataclass, field
from typing import List, Optional, Union
from datetime import datetime

from .base import Ambito, Departamento, Rango, EstadoConsolidacion

from enum import Enum
import hashlib

@dataclass
class Metadata:
    fecha_actualizacion: datetime
    id: str
    ambito: Ambito
    departamento: Departamento
    titulo: str
    rango: Rango
    fecha_disposicion: datetime
    diario: str
    fecha_publicacion: datetime
    diario_numero: str
    fecha_vigencia: Optional[datetime]
    estatus_derogacion: bool
    estatus_anulacion: bool
    vigencia_agotada: bool
    estado_consolidacion: EstadoConsolidacion
    url_eli: str
    url_html_consolidado: str

