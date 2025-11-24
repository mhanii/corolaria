import sys
import os
sys.path.append(os.getcwd())

from src.application.pipeline.embedding_step import EmbeddingGenerator
from src.domain.models.normativa import NormativaCons, Metadata
from src.domain.models.common.node import ArticleNode, NodeType, Node
from unittest.mock import MagicMock

def test_context_formatting():
    print("Testing Context Formatting...")
    
    # 1. Setup Mock Data
    metadata = Metadata(
        titulo="Constitución Española", departamento="Estado", rango="Constitución",
        fecha_actualizacion="", id="BOE-A-1978-31229", ambito="Nacional",
        fecha_disposicion="", diario="BOE", fecha_publicacion="", diario_numero="",
        fecha_vigencia="", estatus_derogacion="", estatus_anulacion="",
        vigencia_agotada=False, estado_consolidacion="", url_eli="", url_html_consolidado=""
    )
    normativa = NormativaCons(
        id="BOE-A-1978-31229", metadata=metadata,
        analysis=MagicMock(), content_tree=MagicMock()
    )
    
    # Create Article with hierarchy
    article = ArticleNode(
        id=1, name="22", level=3, node_type=NodeType.ARTICULO,
        fecha_vigencia="1978-12-29", fecha_caducidad=None
    )
    
    # Create structure: 1. -> a) -> text
    # Item 1
    item1 = Node(id=2, name="1", level=4, node_type=NodeType.APARTADO_NUMERICO)
    item1.text = "Se reconocen y protegen los derechos:"
    article.add_child(item1)
    
    # Item a) under 1
    item_a = Node(id=3, name="a", level=5, node_type=NodeType.APARTADO_ALFA)
    item_a.text = "A expresar y difundir libremente los pensamientos..."
    item1.add_child(item_a)
    
    # Item 2 (Paragraph)
    item2 = Node(id=4, name="2", level=4, node_type=NodeType.APARTADO_NUMERICO)
    item2.text = "El ejercicio de estos derechos no puede restringirse..."
    article.add_child(item2)
    
    # Mock Provider (not used for this test but required for init)
    provider = MagicMock()
    
    generator = EmbeddingGenerator("test_step", provider)
    
    # 2. Test Build Context
    context = generator._build_context_string(normativa, article)
    
    print("\n--- Generated Context ---\n")
    print(context)
    print("\n-------------------------\n")
    
    # 3. Verify Date
    if "Vigente desde 29 de diciembre de 1978" in context:
        print("SUCCESS: Date formatted correctly.")
    else:
        print("FAILURE: Date formatting incorrect.")
        
    # 4. Verify Content Structure
    if "1. Se reconocen" in context:
        print("SUCCESS: Item 1 found with prefix.")
    else:
        print("FAILURE: Item 1 prefix missing.")
        
    if "a) A expresar" in context:
        print("SUCCESS: Item a) found with prefix.")
    else:
        print("FAILURE: Item a) prefix missing.")

    # 5. Test Date Range
    print("\nTesting Date Range...")
    article.fecha_caducidad = "2020-01-01"
    context_range = generator._build_context_string(normativa, article)
    if "hasta 1 de enero de 2020" in context_range:
        print("SUCCESS: Date range formatted correctly.")
    else:
        print("FAILURE: Date range formatting incorrect.")

if __name__ == "__main__":
    test_context_formatting()
