import sys
import os
import shutil
sys.path.append(os.getcwd())

from src.application.pipeline.embedding_step import EmbeddingGenerator
from src.ai.embeddings.factory import EmbeddingFactory
from src.ai.embeddings.json_cache import JSONFileCache
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.models.normativa import NormativaCons, Metadata, Analysis
from src.domain.models.common.node import ArticleNode, NodeType
from src.domain.models.common.base import Ambito, Departamento, Rango, EstadoConsolidacion
from datetime import datetime

class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model, dimensions):
        super().__init__(model, dimensions)
        self.call_count = 0
        
    def get_embedding(self, text: str):
        self.call_count += 1
        return [0.1] * self.dimensions
        
    def get_embeddings(self, texts: list):
        self.call_count += 1
        return [[0.1] * self.dimensions for _ in texts]

def test_caching_flow():
    print("Setting up test data...")
    
    # Clean up previous cache
    cache_file = "data/test_cache.json"
    if os.path.exists(cache_file):
        os.remove(cache_file)
    
    # Mock Data
    metadata = Metadata(
        fecha_actualizacion=datetime.now(),
        id="BOE-TEST-CACHE",
        ambito=Ambito(1),
        departamento=Departamento(1),
        titulo="Ley de Cache",
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
    
    article = ArticleNode(
        id=1,
        name="1",
        level=5,
        node_type=NodeType.ARTICULO,
        text="Texto para cachear.",
        fecha_vigencia="20250101"
    )
    
    normativa = NormativaCons(
        id="BOE-TEST-CACHE",
        metadata=metadata,
        analysis=Analysis(materias=[], referencias_anteriores=[], referencias_posteriores=[]),
        content_tree=article
    )
    
    print("\n--- RUN 1: Expecting Cache MISS ---")
    provider = MockEmbeddingProvider(model="mock", dimensions=10)
    cache = JSONFileCache(cache_file)
    step = EmbeddingGenerator(name="test_caching", provider=provider, cache=cache)
    
    step.process((normativa, []))
    
    print(f"Provider calls: {provider.call_count}")
    if provider.call_count == 1:
        print("SUCCESS: Provider called once.")
    else:
        print(f"FAILURE: Provider called {provider.call_count} times.")
        
    # Check file existence
    if os.path.exists(cache_file):
        print("SUCCESS: Cache file created.")
    else:
        print("FAILURE: Cache file not created.")

    print("\n--- RUN 2: Expecting Cache HIT ---")
    # Reset provider count, reload cache
    provider.call_count = 0
    cache = JSONFileCache(cache_file) # Reloads from disk
    step = EmbeddingGenerator(name="test_caching", provider=provider, cache=cache)
    
    # Reset article embedding to force check
    article.embedding = None
    
    step.process((normativa, []))
    
    print(f"Provider calls: {provider.call_count}")
    if provider.call_count == 0:
        print("SUCCESS: Provider NOT called (Cache Hit).")
    else:
        print(f"FAILURE: Provider called {provider.call_count} times.")
        
    if article.embedding is not None:
        print("SUCCESS: Article has embedding.")
    else:
        print("FAILURE: Article missing embedding.")

    # Cleanup
    if os.path.exists(cache_file):
        os.remove(cache_file)

if __name__ == "__main__":
    test_caching_flow()
