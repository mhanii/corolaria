class IndiceDocumentoLegal:
    """Índice invertido para búsqueda rápida de elementos legales"""
    
    def __init__(self, documento: DocumentoLegal):
        self.documento = documento
        self.indice_por_articulo: Dict[str, NodoLegal] = {}
        self.indice_por_cita: Dict[str, NodoLegal] = {}
        self.indice_por_tipo: Dict[str, List[NodoLegal]] = {}
        self.indice_textual: Dict[str, List[NodoLegal]] = {}
        self._construir_indices()
    
    def _construir_indices(self):
        """Construye todos los índices usando el patrón Visitor"""
        visitante = VisitanteGeneradorCitas(self.documento.metadatos_documento)
        self.documento.aceptar(visitante)
        self.indice_por_cita = visitante.indice_citas
        
        # Construir otros índices
        self._indexar_recursivo(self.documento)
    
    def _indexar_recursivo(self, nodo: NodoLegal):
        """Indexa recursivamente todos los nodos"""
        # Índice por tipo
        if nodo.tipo not in self.indice_por_tipo:
            self.indice_por_tipo[nodo.tipo] = []
        self.indice_por_tipo[nodo.tipo].append(nodo)
        
        # Índice por artículo
        if nodo.tipo == "articulo" and nodo.numero:
            self.indice_por_articulo[nodo.numero] = nodo
        
        # Índice textual
        if isinstance(nodo, NodoHoja) and nodo.contenido:
            palabras = nodo.contenido.lower().split()
            for palabra in palabras:
                if palabra not in self.indice_textual:
                    self.indice_textual[palabra] = []
                self.indice_textual[palabra].append(nodo)
        
        # Recursión
        for hijo in nodo.hijos:
            self._indexar_recursivo(hijo)
    
    def buscar_articulo(self, numero: str) -> Optional[NodoLegal]:
        """Busca un artículo por número"""
        return self.indice_por_articulo.get(numero)
    
    def buscar_por_cita(self, cita: str) -> Optional[NodoLegal]:
        """Busca un elemento por su cita corta"""
        return self.indice_por_cita.get(cita)
    
    def buscar_texto(self, query: str) -> List[Tuple[NodoLegal, float]]:
        """Busca nodos que contengan el texto (búsqueda simple)"""
        palabras_query = query.lower().split()
        resultados: Dict[NodoLegal, int] = {}
        
        for palabra in palabras_query:
            nodos = self.indice_textual.get(palabra, [])
            for nodo in nodos:
                resultados[nodo] = resultados.get(nodo, 0) + 1
        
        # Ordenar por relevancia
        return sorted(
            [(nodo, score) for nodo, score in resultados.items()],
            key=lambda x: x[1],
            reverse=True
        )
