from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class TipoNumeracion(Enum):
    """Tipos de numeración posibles en textos legales"""
    ROMANO = "romano"          # I, II, III, IV
    ARABIGO = "arabigo"        # 1, 2, 3, 4
    ORDINAL = "ordinal"        # primero, segundo
    LETRA_MINUSCULA = "letra_minuscula"  # a, b, c
    LETRA_MAYUSCULA = "letra_mayuscula"  # A, B, C
    ALFANUMERICO = "alfanumerico"        # 1.1, 1.2, 2.1

@dataclass
class PosicionTexto:
    """Captura la posición exacta en el texto original"""
    inicio: int  # Índice de inicio en caracteres
    fin: int     # Índice de fin en caracteres
    linea_inicio: Optional[int] = None
    linea_fin: Optional[int] = None
    pagina: Optional[int] = None

@dataclass
class MetadatosDocumento:
    """Metadatos del documento legal completo"""
    tipo_documento: str  # "constitucion", "codigo_penal", "ley_organica", etc.
    titulo_completo: str
    titulo_abreviado: Optional[str] = None
    numero: Optional[str] = None  # "10/1995"
    fecha_promulgacion: Optional[str] = None
    boe_numero: Optional[str] = None
    boe_fecha: Optional[str] = None
    url_boe: Optional[str] = None

class NodoLegal(ABC):
    """Clase base abstracta para todos los nodos del árbol legal"""
    
    def __init__(
        self,
        tipo: str,
        numero: Optional[str] = None,
        tipo_numeracion: Optional[TipoNumeracion] = None,
        titulo: Optional[str] = None,
        contenido: Optional[str] = None,
        posicion: Optional[PosicionTexto] = None
    ):
        self.tipo = tipo
        self.numero = numero
        self.tipo_numeracion = tipo_numeracion
        self.titulo = titulo
        self.contenido = contenido
        self.posicion = posicion
        self.padre: Optional['NodoLegal'] = None
        self.hijos: List['NodoLegal'] = []
        self.metadatos: Dict[str, Any] = {}
        
    def agregar_hijo(self, hijo: 'NodoLegal') -> None:
        """Agrega un hijo y establece la relación bidireccional"""
        hijo.padre = self
        self.hijos.append(hijo)
    
    def obtener_ruta_completa(self) -> List['NodoLegal']:
        """Devuelve la ruta completa desde la raíz hasta este nodo"""
        ruta = []
        nodo_actual = self
        while nodo_actual:
            ruta.insert(0, nodo_actual)
            nodo_actual = nodo_actual.padre
        return ruta
    
    def obtener_referencia_legal(self, metadatos_doc: MetadatosDocumento) -> str:
        """
        Genera la referencia legal completa según convenciones españolas.
        Ejemplos:
        - "art. 14 CE"
        - "art. 138 del Libro II del Código Penal"
        - "Disposición Adicional Primera de la Ley Orgánica 10/1995"
        """
        ruta = self.obtener_ruta_completa()
        
        # Construir la referencia de forma jerárquica
        partes = []
        
        for nodo in ruta[1:]:  # Saltar el documento raíz
            if nodo.tipo == "articulo":
                if nodo.numero:
                    partes.insert(0, f"art. {nodo.numero}")
            elif nodo.tipo == "apartado":
                if nodo.numero and partes:
                    partes[0] += f".{nodo.numero}"
            elif nodo.tipo == "letra":
                if nodo.numero and partes:
                    partes[0] += f".{nodo.numero}"
            elif nodo.tipo in ["libro", "titulo", "capitulo", "seccion"]:
                if nodo.numero and nodo.tipo != "articulo":
                    nombre_tipo = nodo.tipo.capitalize()
                    partes.append(f"{nombre_tipo} {nodo.numero}")
            elif nodo.tipo.startswith("disposicion"):
                tipo_disp = " ".join([p.capitalize() for p in nodo.tipo.split("_")])
                partes.insert(0, f"{tipo_disp} {nodo.numero}")
        
        # Añadir el documento al final
        if metadatos_doc.titulo_abreviado:
            referencia = " del ".join(partes) + f" {metadatos_doc.titulo_abreviado}"
        else:
            referencia = " del ".join(partes) + f" {metadatos_doc.titulo_completo}"
        
        return referencia
    
    def obtener_cita_corta(self) -> str:
        """
        Genera una cita corta para uso interno.
        Ejemplo: "CE.art.14.1.a" o "CP.L2.T1.art.138"
        """
        ruta = self.obtener_ruta_completa()
        partes = []
        
        for nodo in ruta[1:]:
            if nodo.tipo == "libro":
                partes.append(f"L{nodo.numero}")
            elif nodo.tipo == "titulo":
                partes.append(f"T{nodo.numero}")
            elif nodo.tipo == "capitulo":
                partes.append(f"C{nodo.numero}")
            elif nodo.tipo == "seccion":
                partes.append(f"S{nodo.numero}")
            elif nodo.tipo == "articulo":
                partes.append(f"art.{nodo.numero}")
            elif nodo.tipo == "apartado":
                partes.append(nodo.numero)
            elif nodo.tipo == "letra":
                partes.append(nodo.numero)
        
        return ".".join(partes)
    
    @abstractmethod
    def aceptar(self, visitante: 'VisitanteLegal') -> Any:
        """Patrón Visitor para operaciones flexibles"""
        pass

class NodoContenedor(NodoLegal):
    """Nodo que puede contener otros nodos (Composite)"""
    
    def aceptar(self, visitante: 'VisitanteLegal') -> Any:
        return visitante.visitar_contenedor(self)

class NodoHoja(NodoLegal):
    """Nodo terminal que contiene texto (Leaf)"""
    
    def aceptar(self, visitante: 'VisitanteLegal') -> Any:
        return visitante.visitar_hoja(self)

class DocumentoLegal(NodoContenedor):
    """Nodo raíz que representa todo el documento legal"""
    
    def __init__(self, metadatos: MetadatosDocumento):
        super().__init__(tipo="documento", titulo=metadatos.titulo_completo)
        self.metadatos_documento = metadatos
