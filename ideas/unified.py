import re
from typing import Tuple

class ParserLegalUnificado:
    """Parser unificado que funciona con cualquier configuración"""
    
    def __init__(self, config: ConfiguracionEstructura, metadatos: MetadatosDocumento):
        self.config = config
        self.metadatos = metadatos
        self.documento = DocumentoLegal(metadatos)
        self._compilar_patrones()
    
    def _compilar_patrones(self):
        """Compila los patrones regex una sola vez"""
        self.patrones_compilados = {}
        for nivel in self.config.jerarquia:
            self.patrones_compilados[nivel["tipo"]] = re.compile(
                nivel["patron"], 
                re.MULTILINE | re.IGNORECASE
            )
    
    def parsear(self, texto: str) -> DocumentoLegal:
        """Parsea el texto completo y construye el árbol"""
        lineas = texto.split('\n')
        self._parsear_recursivo(texto, lineas, self.documento, 0, 0)
        return self.documento
    
    def _parsear_recursivo(
        self, 
        texto: str, 
        lineas: List[str],
        nodo_padre: NodoLegal, 
        nivel_jerarquia: int,
        indice_linea: int
    ) -> int:
        """
        Parsea recursivamente el texto según la jerarquía configurada.
        Retorna el índice de la última línea procesada.
        """
        if nivel_jerarquia >= len(self.config.jerarquia):
            # Hemos llegado al nivel más profundo, capturar contenido
            return self._capturar_contenido(texto, lineas, nodo_padre, indice_linea)
        
        nivel_actual = self.config.jerarquia[nivel_jerarquia]
        patron = self.patrones_compilados[nivel_actual["tipo"]]
        
        i = indice_linea
        while i < len(lineas):
            linea = lineas[i]
            match = patron.match(linea.strip())
            
            if match:
                # Encontramos un elemento de este nivel
                numero = match.group(1) if match.groups() else None
                
                # Crear nodo
                if nivel_jerarquia == len(self.config.jerarquia) - 1:
                    # Es una hoja (artículo final o contenido)
                    nuevo_nodo = NodoHoja(
                        tipo=nivel_actual["tipo"],
                        numero=numero,
                        tipo_numeracion=nivel_actual.get("numeracion")
                    )
                else:
                    # Es un contenedor
                    nuevo_nodo = NodoContenedor(
                        tipo=nivel_actual["tipo"],
                        numero=numero,
                        tipo_numeracion=nivel_actual.get("numeracion")
                    )
                
                # Capturar posición
                inicio_caracter = sum(len(l) + 1 for l in lineas[:i])
                nuevo_nodo.posicion = PosicionTexto(
                    inicio=inicio_caracter,
                    fin=inicio_caracter + len(linea),
                    linea_inicio=i + 1
                )
                
                nodo_padre.agregar_hijo(nuevo_nodo)
                
                # Parsear recursivamente el contenido de este nodo
                i = self._parsear_recursivo(
                    texto, lineas, nuevo_nodo, nivel_jerarquia + 1, i + 1
                )
            else:
                # No es un elemento de este nivel, pasar al siguiente nivel
                i += 1
        
        return i
    
    def _capturar_contenido(
        self, 
        texto: str, 
        lineas: List[str], 
        nodo_padre: NodoLegal, 
        indice_inicio: int
    ) -> int:
        """Captura el contenido de texto de un nodo"""
        contenido_lineas = []
        i = indice_inicio
        
        # Capturar hasta encontrar el siguiente elemento del mismo nivel o superior
        while i < len(lineas):
            linea = lineas[i]
            
            # Verificar si es inicio de un nuevo elemento
            es_nuevo_elemento = False
            for nivel in self.config.jerarquia:
                patron = self.patrones_compilados[nivel["tipo"]]
                if patron.match(linea.strip()):
                    es_nuevo_elemento = True
                    break
            
            if es_nuevo_elemento:
                break
            
            contenido_lineas.append(linea)
            i += 1
        
        # Asignar contenido al nodo padre
        if isinstance(nodo_padre, NodoHoja):
            nodo_padre.contenido = '\n'.join(contenido_lineas).strip()
            
            # Actualizar posición final
            if nodo_padre.posicion:
                fin_caracter = sum(len(l) + 1 for l in lineas[:i])
                nodo_padre.posicion.fin = fin_caracter
                nodo_padre.posicion.linea_fin = i
        
        return i
