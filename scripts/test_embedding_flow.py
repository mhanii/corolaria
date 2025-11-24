import sys
import os
sys.path.append(os.getcwd())

from src.application.pipeline.embedding_step import EmbeddingGenerator
from src.ai.embeddings.factory import EmbeddingFactory
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.models.normativa import NormativaCons, Metadata, Analysis
from src.domain.models.common.node import ArticleNode, NodeType
from src.domain.models.common.base import Ambito, Departamento, Rango, EstadoConsolidacion
from datetime import datetime

def test_embedding_flow():
    print("Setting up test data...")
    
    # Mock Metadata
    metadata = Metadata(
        fecha_actualizacion=datetime.now(),
        id="BOE-TEST-2025",
        ambito=Ambito(1), # 1 = Nacional (assumed)
        departamento=Departamento(1),
        titulo="Ley de Prueba",
        rango=Rango(1),
        fecha_disposicion=datetime.now(),
        diario="BOE",
        fecha_publicacion=datetime.now(),
        diario_numero="1",
        fecha_vigencia=datetime.now(),
        estatus_derogacion=False,
        estatus_anulacion=False,
        vigencia_agotada=False,
        estado_consolidacion=EstadoConsolidacion(1),
        url_eli="",
        url_html_consolidado=""
    )
    
    # Mock Article Node
    article = ArticleNode(
        id=1,
        name="1",
        level=5,
        node_type=NodeType.ARTICULO,
        text="Este es el texto del artículo de prueba.",
        fecha_vigencia="20250101"
    )
    
    # Mock Normativa
    normativa = NormativaCons(
        id="BOE-TEST-2025",
        metadata=metadata,
        analysis=Analysis(materias=[], referencias_anteriores=[], referencias_posteriores=[]),
        content_tree=article
    )
    
    class MockEmbeddingProvider(EmbeddingProvider):
        def get_embedding(self, text: str):
            return [0.1] * 384
        def get_embeddings(self, texts: list):
            return [[0.1] * 384 for _ in texts]

    print("Initializing EmbeddingGenerator with Mock provider...")
    try:
        # provider = EmbeddingFactory.create(provider="huggingface")
        provider = MockEmbeddingProvider(model="mock", dimensions=384)
        step = EmbeddingGenerator(name="test_embedding", provider=provider)
        
        print("Running process...")
        # Pipeline passes (normativa, change_events)
        result_normativa, _ = step.process((normativa, []))
        
        print("Verifying results...")
        if result_normativa.content_tree.embedding is not None:
            emb_len = len(result_normativa.content_tree.embedding)
            print(f"SUCCESS: Embedding generated with dimension {emb_len}")
            if emb_len == 384:
                print("Dimension matches expected default for all-MiniLM-L6-v2")
            else:
                print(f"WARNING: Dimension {emb_len} differs from expected 384")
            
            # Verify context string was built (we can't easily check the string itself without inspecting the step internals, 
            # but if we got an embedding, the loop ran)
        else:
            print("FAILURE: No embedding found on ArticleNode")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_embedding_flow()
