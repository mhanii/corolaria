"""
QRAG Context Collector.

Query-optimized RAG collector that uses an LLM to generate optimized search queries
before performing vector search. Improves retrieval quality for complex questions.
"""
import json
from typing import List, Dict, Any, Optional

from src.domain.interfaces.context_collector import ContextCollector, ContextResult
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.llm_provider import LLMProvider, Message
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.ai.context_collectors.chunk_enricher import ChunkEnricher
from src.utils.logger import step_logger

# Import tracer for Phoenix observability
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("qrag_collector")
except ImportError:
    _tracer = None


class QRAGCollector(ContextCollector):
    """
    Query-optimized RAG collector.
    
    Uses an LLM to generate optimized search queries from the user's input,
    then performs vector search for each query and merges the results.
    
    This approach improves retrieval for:
    - Complex multi-topic questions
    - Vague or conversational queries
    - Questions requiring multiple pieces of information
    
    Attributes:
        neo4j_adapter: Neo4j adapter for vector search
        embedding_provider: Provider to generate query embeddings
        llm_provider: LLM for query generation
        index_name: Name of the vector index to search
        max_queries: Maximum number of queries the LLM can generate
        max_results: Final limit on results after merging (lowest scores trimmed)
    """
    
    QUERY_GENERATION_PROMPT = '''Eres un generador de consultas de búsqueda para un sistema RAG de documentos legales españoles.

TU ÚNICO PROPÓSITO: Generar consultas para buscar leyes españolas.

ENTRADA: Una pregunta del usuario sobre derecho español
SALIDA: Un JSON array de strings con consultas de búsqueda optimizadas

REGLAS ESTRICTAS:
1. Las consultas deben hablar con conceptos jurídicos mencionados en la pregunta
2. Si la pregunta es simple (un tema), genera UNA sola consulta
3. Si tiene múltiples temas legales, genera consultas separadas (máximo {max_queries})
4. Si hay más de un concepto jurídico, como preguntas tipo test, cada consulta debe hablar sobre un concepto
5. Las consultas deben usar TERMINOLOGÍA JURÍDICA precisa, pero al mismo modo deben ser preguntas.
6. Solo menciona leyes especificos si esta en la pregunta.
7. Responde SOLO con el JSON array, sin explicaciones

PROHIBIDO - NO generes consultas para:
- Búsquedas tipo Google ("cómo hacer...", "pasos para...", "redactar documento")
- Servicios o trámites administrativos
- Consejos prácticos o tutoriales
- Temas no relacionados con legislación española

Si la pregunta NO es sobre legislación española o no se puede convertir en búsqueda de artículos legales, responde: ["consulta no válida para RAG legal"]

EJEMPLOS CORRECTOS:
Usuario: "¿Qué dice la constitución sobre igualdad?"
Salida: ["¿Qué dice la constitución sobre igualdad?"]

Usuario: "Obligaciones del arrendador y arrendatario"
Salida: ["¿Qué obligaciones tiene el arrendador?", "¿Qué obligaciones tiene el arrendatario?"]

Usuario: "¿Cuál es el plazo de prescripción de deudas?"
Salida: ["¿Cuál es el plazo de prescripción de deudas?", "¿Cuál es son los tipos de deudas?", "¿El plazo de prescripción varía según el tipo de deuda?"]

Usuario: "Derechos fundamentales y libertad de expresión"
Salida: ["Cuales son los derechos fundamentales?", "Libertad de expresión"]

EJEMPLOS INCORRECTOS (no generar):
Usuario: "Cómo redactar un contrato" → NO es búsqueda de artículos
Usuario: "Pasos para divorciarse" → NO es búsqueda de artículos (buscar "¿Cuales son los pasos para divorciarse?" sí sería válido)

Usuario: "{user_query}"
Salida:'''

    def __init__(
        self, 
        neo4j_adapter: GraphAdapter,
        embedding_provider: EmbeddingProvider,
        llm_provider: LLMProvider,
        index_name: str = "article_embeddings",
        max_queries: int = 5,
        max_results: int = 10,
        enrich: bool = True
    ):
        """
        Initialize the QRAG context collector.
        
        Args:
            neo4j_adapter: Graph adapter for database queries (implements GraphAdapter)
            embedding_provider: Provider to generate query embeddings
            llm_provider: LLM for generating optimized queries
            index_name: Name of the vector index (default: "article_embeddings")
            max_queries: Maximum queries the LLM can generate (default: 5)
            max_results: Final limit after merging results (default: 10)
            enrich: Whether to apply ChunkEnricher (version hopping, reference expansion).
                    Default True. Set False for raw vector search results.
        """
        self._neo4j_adapter = neo4j_adapter
        self._embedding_provider = embedding_provider
        self._llm_provider = llm_provider
        self._index_name = index_name
        self._max_queries = max_queries
        self._max_results = max_results
        self._enrich = enrich
        self._enricher = ChunkEnricher(neo4j_adapter) if enrich else None
        
        step_logger.info(
            f"[QRAGCollector] Initialized with index '{index_name}', "
            f"max_queries={max_queries}, max_results={max_results}, enrich={enrich}"
        )
    
    @property
    def name(self) -> str:
        """Human-readable name of this collector."""
        return "QRAGCollector"
    
    def collect(
        self, 
        query: str, 
        top_k: int = 5,
        **kwargs
    ) -> ContextResult:
        """
        Collect context using LLM-generated search queries.
        
        Args:
            query: The user's query
            top_k: Results to retrieve per generated query
            **kwargs:
                - index_name: Override the default index name
                - max_queries: Override max queries limit
                - max_results: Override max results limit
                
        Returns:
            ContextResult with retrieved and merged chunks
        """
        index_name = kwargs.get("index_name", self._index_name)
        max_queries = kwargs.get("max_queries", self._max_queries)
        max_results = kwargs.get("max_results", self._max_results)
        
        # Configure enricher if enabled
        if self._enricher:
            max_refs = kwargs.get("max_refs", ChunkEnricher.DEFAULT_MAX_REFS)
            self._enricher.max_refs = max_refs
        
        # Use proper context manager for tracing
        if _tracer:
            with _tracer.start_as_current_span("QRAGCollector.collect") as span:
                # Record input attributes
                span.set_attribute("collector.name", self.name)
                span.set_attribute("input.query", query)
                span.set_attribute("input.top_k", top_k)
                span.set_attribute("input.max_queries", max_queries)
                span.set_attribute("input.max_results", max_results)
                
                # Step 1: Generate optimized search queries using LLM
                step_logger.info(f"[QRAGCollector] Generating search queries for: '{query[:50]}...'")
                
                with _tracer.start_as_current_span("QRAGCollector.generate_queries") as gen_span:
                    gen_span.set_attribute("input.user_query", query)
                    gen_span.set_attribute("input.max_queries", max_queries)
                    generated_queries = self._generate_queries(query, max_queries)
                    gen_span.set_attribute("output.query_count", len(generated_queries))
                    gen_span.set_attribute("output.queries", str(generated_queries))
                
                if not generated_queries:
                    step_logger.warning("[QRAGCollector] No queries generated, falling back to original query")
                    generated_queries = [query]
                
                span.set_attribute("generated_queries", str(generated_queries))
                step_logger.info(f"[QRAGCollector] Generated {len(generated_queries)} queries: {generated_queries}")
                
                # Step 2: Run vector search for each query
                all_chunks: List[Dict[str, Any]] = []
                seen_ids = set()
                
                for i, search_query in enumerate(generated_queries):
                    step_logger.info(f"[QRAGCollector] Query {i+1}/{len(generated_queries)}: '{search_query}'")
                    
                    with _tracer.start_as_current_span(f"QRAGCollector.vector_search_{i+1}") as search_span:
                        search_span.set_attribute("input.query", search_query)
                        search_span.set_attribute("input.query_index", i + 1)
                        search_span.set_attribute("input.top_k", top_k)
                        
                        query_embedding = self._embedding_provider.get_embedding(search_query)
                        chunks = self._neo4j_adapter.vector_search(
                            query_embedding=query_embedding,
                            top_k=top_k,
                            index_name=index_name
                        )
                        search_span.set_attribute("output.results_count", len(chunks))
                    
                    # Append results (avoiding duplicates by article_id)
                    for chunk in chunks:
                        article_id = chunk.get("article_id")
                        if article_id and article_id not in seen_ids:
                            seen_ids.add(article_id)
                            chunk["source_query"] = search_query
                            chunk["query_index"] = i
                            all_chunks.append(chunk)
                
                step_logger.info(f"[QRAGCollector] Total unique chunks collected: {len(all_chunks)}")
                
                # Step 3: Sort by score and trim to max_results
                all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
                final_chunks = all_chunks[:max_results]
                
                # Step 4: Enrich chunks with validity checking and reference expansion (if enabled)
                if self._enricher:
                    final_chunks = self._enricher.enrich_chunks(final_chunks)
                
                step_logger.info(f"[QRAGCollector] Final chunks after enrichment: {len(final_chunks)}")
                
                # Record output attributes
                span.set_attribute("output.total_chunks", len(all_chunks))
                span.set_attribute("output.final_chunks", len(final_chunks))
                span.set_attribute("output.queries_used", len(generated_queries))
                
                # Log full chunk details for each retrieved chunk
                for i, chunk in enumerate(final_chunks):
                    span.set_attribute(f"output.chunk_{i}.article_number", chunk.get('article_number', 'N/A'))
                    span.set_attribute(f"output.chunk_{i}.normativa_title", chunk.get('normativa_title', 'N/A'))
                    span.set_attribute(f"output.chunk_{i}.score", chunk.get('score', 0))
                    span.set_attribute(f"output.chunk_{i}.source_query", chunk.get('source_query', 'N/A'))
                    span.set_attribute(f"output.chunk_{i}.text", chunk.get('text', ''))
                
                return ContextResult(
                    chunks=final_chunks,
                    strategy_name=self.name,
                    metadata={
                        "index_name": index_name,
                        "original_query": query,
                        "generated_queries": generated_queries,
                        "top_k_per_query": top_k,
                        "max_results": max_results,
                        "total_before_trim": len(all_chunks),
                        "total_after_trim": len(final_chunks)
                    }
                )
        else:
            # No tracing - execute directly
            step_logger.info(f"[QRAGCollector] Generating search queries for: '{query[:50]}...'")
            generated_queries = self._generate_queries(query, max_queries)
            
            if not generated_queries:
                step_logger.warning("[QRAGCollector] No queries generated, falling back to original query")
                generated_queries = [query]
            
            step_logger.info(f"[QRAGCollector] Generated {len(generated_queries)} queries: {generated_queries}")
            
            all_chunks: List[Dict[str, Any]] = []
            seen_ids = set()
            
            for i, search_query in enumerate(generated_queries):
                step_logger.info(f"[QRAGCollector] Query {i+1}/{len(generated_queries)}: '{search_query}'")
                
                query_embedding = self._embedding_provider.get_embedding(search_query)
                chunks = self._neo4j_adapter.vector_search(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    index_name=index_name
                )
                
                for chunk in chunks:
                    article_id = chunk.get("article_id")
                    if article_id and article_id not in seen_ids:
                        seen_ids.add(article_id)
                        chunk["source_query"] = search_query
                        chunk["query_index"] = i
                        all_chunks.append(chunk)
            
            step_logger.info(f"[QRAGCollector] Total unique chunks collected: {len(all_chunks)}")
            
            all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
            final_chunks = all_chunks[:max_results]
            
            # Enrich chunks with validity checking and reference expansion (if enabled)
            if self._enricher:
                final_chunks = self._enricher.enrich_chunks(final_chunks)
            
            step_logger.info(f"[QRAGCollector] Final chunks after enrichment: {len(final_chunks)}")
            
            return ContextResult(
                chunks=final_chunks,
                strategy_name=self.name,
                metadata={
                    "index_name": index_name,
                    "original_query": query,
                    "generated_queries": generated_queries,
                    "top_k_per_query": top_k,
                    "max_results": max_results,
                    "total_before_trim": len(all_chunks),
                    "total_after_trim": len(final_chunks)
                }
            )
    
    def _generate_queries(self, user_query: str, max_queries: int) -> List[str]:
        """
        Generate optimized search queries using the LLM.
        
        Args:
            user_query: Original user query
            max_queries: Maximum number of queries to generate
            
        Returns:
            List of generated search query strings
        """
        # Build prompt with max_queries injected
        prompt = self.QUERY_GENERATION_PROMPT.format(
            max_queries=max_queries,
            user_query=user_query
        )
        
        try:
            # Call LLM for query generation
            response = self._llm_provider.generate(
                messages=[Message(role="user", content=prompt)],
                context=None,
                system_prompt=None
            )
            
            # Parse JSON response
            raw_response = response.content.strip()
            
            # Handle potential markdown code blocks
            if raw_response.startswith("```"):
                # Extract JSON from code block
                lines = raw_response.split("\n")
                json_lines = [l for l in lines if not l.startswith("```")]
                raw_response = "\n".join(json_lines).strip()
            
            queries = json.loads(raw_response)
            
            if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                # Limit to max_queries
                return queries[:max_queries]
            else:
                step_logger.warning(f"[QRAGCollector] Invalid query format: {raw_response}")
                return []
                
        except json.JSONDecodeError as e:
            step_logger.warning(f"[QRAGCollector] Failed to parse LLM response as JSON: {e}")
            return []
        except Exception as e:
            step_logger.error(f"[QRAGCollector] Query generation failed: {e}")
            return []
