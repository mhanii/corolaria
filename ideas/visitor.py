class VisitanteLegal(ABC):
    """Interfaz para visitantes que operan sobre el árbol legal"""
    
    @abstractmethod
    def visitar_contenedor(self, nodo: NodoContenedor) -> Any:
        pass
    
    @abstractmethod
    def visitar_hoja(self, nodo: NodoHoja) -> Any:
        pass

class VisitanteBusqueda(VisitanteLegal):
    """Busca artículos específicos en el árbol"""
    
    def __init__(self, criterio: str):
        self.criterio = criterio
        self.resultados = []
    
    def visitar_contenedor(self, nodo: NodoContenedor) -> None:
        if self._cumple_criterio(nodo):
            self.resultados.append(nodo)
        for hijo in nodo.hijos:
            hijo.aceptar(self)
    
    def visitar_hoja(self, nodo: NodoHoja) -> None:
        if self._cumple_criterio(nodo):
            self.resultados.append(nodo)
    
    def _cumple_criterio(self, nodo: NodoLegal) -> bool:
        # Implementar lógica de búsqueda
        if nodo.tipo == "articulo" and nodo.numero == self.criterio:
            return True
        return False

class VisitanteGeneradorCitas(VisitanteLegal):
    """Genera todas las citas posibles del documento"""
    
    def __init__(self, metadatos_doc: MetadatosDocumento):
        self.metadatos_doc = metadatos_doc
        self.indice_citas: Dict[str, NodoLegal] = {}
    
    def visitar_contenedor(self, nodo: NodoContenedor) -> None:
        if nodo.tipo in ["articulo", "disposicion_adicional", 
                         "disposicion_transitoria", "disposicion_final"]:
            cita = nodo.obtener_cita_corta()
            self.indice_citas[cita] = nodo
        
        for hijo in nodo.hijos:
            hijo.aceptar(self)
    
    def visitar_hoja(self, nodo: NodoHoja) -> None:
        if nodo.tipo in ["articulo", "apartado", "letra"]:
            cita = nodo.obtener_cita_corta()
            self.indice_citas[cita] = nodo

class VisitanteExportadorJSON(VisitanteLegal):
    """Exporta el árbol a formato JSON para almacenamiento"""
    
    def visitar_contenedor(self, nodo: NodoContenedor) -> Dict:
        return {
            "tipo": nodo.tipo,
            "numero": nodo.numero,
            "titulo": nodo.titulo,
            "posicion": self._serializar_posicion(nodo.posicion),
            "hijos": [hijo.aceptar(self) for hijo in nodo.hijos],
            "metadatos": nodo.metadatos
        }
    
    def visitar_hoja(self, nodo: NodoHoja) -> Dict:
        return {
            "tipo": nodo.tipo,
            "numero": nodo.numero,
            "titulo": nodo.titulo,
            "contenido": nodo.contenido,
            "posicion": self._serializar_posicion(nodo.posicion),
            "metadatos": nodo.metadatos
        }
    
    def _serializar_posicion(self, pos: Optional[PosicionTexto]) -> Optional[Dict]:
        if pos:
            return {
                "inicio": pos.inicio,
                "fin": pos.fin,
                "linea_inicio": pos.linea_inicio,
                "linea_fin": pos.linea_fin,
                "pagina": pos.pagina
            }
        return None
