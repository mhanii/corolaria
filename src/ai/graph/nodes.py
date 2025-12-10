"""
LangGraph Nodes for Chat Workflow.
Each node represents a step in the RAG pipeline.
"""
import json
import time
from typing import Dict, Any

from src.ai.graph.state import ChatGraphState
from src.domain.interfaces.llm_provider import Message
from src.utils.logger import step_logger

# Import tracer for Phoenix observability
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("langgraph_nodes")
except ImportError:
    _tracer = None


def collect_context_node(
    state: ChatGraphState, 
    *, 
    context_collector
) -> Dict[str, Any]:
    """
    Collect context using the configured ContextCollector strategy.
    
    This node checks if context collection should be skipped (for follow-up queries)
    and either reuses previous context or runs the context collector.
    
    Args:
        state: Current workflow state
        context_collector: ContextCollector implementation to use
        
    Returns:
        State update with collected chunks, strategy name, and context_json
    """
    # Check if we should skip context collection (for follow-up queries)
    if state.get("skip_collector") and state.get("previous_context"):
        step_logger.info("[CollectContextNode] Skipping collector, reusing previous context")
        
        # Parse previous context back to chunks for citation processing
        previous_chunks = []
        try:
            previous_chunks = json.loads(state["previous_context"])
        except (json.JSONDecodeError, TypeError):
            step_logger.warning("[CollectContextNode] Failed to parse previous context, running collector")
            # Fall through to normal collection
        else:
            return {
                "chunks": previous_chunks,
                "context_strategy": "reused_previous",
                "context_json": state["previous_context"]
            }
    
    # Normal path: collect context via configured strategy
    step_logger.info(f"[CollectContextNode] Collecting context using {context_collector.name}...")
    
    result = context_collector.collect(
        query=state["query"],
        top_k=state["top_k"]
    )
    
    step_logger.info(f"[CollectContextNode] Collected {len(result)} chunks via {result.strategy_name}")
    
    # Serialize chunks for storage
    context_json = json.dumps(result.chunks, ensure_ascii=False, default=str)
    
    return {
        "chunks": result.chunks,
        "context_strategy": result.strategy_name,
        "context_json": context_json
    }


def build_citations_node(
    state: ChatGraphState, 
    *,
    citation_engine
) -> Dict[str, Any]:
    """
    Create citations from chunks and format context.
    
    This node builds the context that will be sent to the LLM.
    Includes context history with configurable depth:
    - Immediate previous: ALL chunks (full context)
    - Older contexts: Only chunks that were used for citations
    
    ALL sources are combined into a single citations list so the LLM
    can cite from any context source (historical or current).
    
    DEDUPLICATION: Chunks with the same article_id are deduplicated,
    keeping the first occurrence (priority: history → current).
    
    Args:
        state: Current workflow state
        citation_engine: Engine for citation management
        
    Returns:
        State update with citations and formatted context
    """
    # Deduplication stats for tracing
    dedup_stats = {
        "total_chunks_input": 0,
        "unique_chunks": 0,
        "duplicates_skipped": 0,
        "skipped_article_ids": []
    }
    
    # Collect ALL chunks from all sources for unified citation indexing
    all_chunks = []
    context_parts = []
    citation_index = 1  # Start indexing at 1
    seen_article_ids = set()  # Track seen articles for deduplication
    
    def add_chunk_if_unique(chunk: dict, label_chunks: list, source: str) -> bool:
        """Add chunk to label_chunks if article_id not seen. Returns True if added."""
        nonlocal citation_index
        dedup_stats["total_chunks_input"] += 1
        
        article_id = chunk.get("article_id")
        if article_id and article_id in seen_article_ids:
            dedup_stats["duplicates_skipped"] += 1
            dedup_stats["skipped_article_ids"].append(f"{source}:{article_id}")
            step_logger.debug(f"[CitationsNode] DEDUP: Skipping duplicate {article_id} from {source}")
            return False  # Skip duplicate
        
        if article_id:
            seen_article_ids.add(article_id)
        chunk["_citation_index"] = citation_index
        label_chunks.append(chunk)
        all_chunks.append(chunk)
        citation_index += 1
        dedup_stats["unique_chunks"] += 1
        return True
    
    # Check if we're reusing previous context (skip_collector=True)
    is_reusing = state.get("context_strategy") == "reused_previous"
    
    # Include context history if available AND we're not reusing it
    context_history = state.get("context_history", [])
    
    if context_history and not is_reusing:
        step_logger.info(f"[CitationsNode] Processing {len(context_history)} context history entries...")
        
        for i, entry in enumerate(context_history):
            try:
                is_immediate = entry.get("is_immediate", False)
                source_name = "immediate" if is_immediate else f"history_{i+1}"
                
                if is_immediate:
                    # Immediate previous: include ALL chunks
                    chunks = json.loads(entry["context_json"])
                    label = "=== CONTEXTO PREVIO INMEDIATO (de la última respuesta) ==="
                else:
                    # Older contexts: only include used citations
                    used_citations = entry.get("citations", [])
                    if not used_citations:
                        continue  # Skip if no citations were used
                    
                    # Convert Citation objects to chunks
                    chunks = [
                        {
                            "article_id": c.article_id,
                            "article_number": c.article_number,
                            "article_text": c.article_text,
                            "normativa_title": c.normativa_title,
                            "article_path": c.article_path,
                            "score": c.score
                        }
                        for c in used_citations
                    ]
                    label = f"=== CONTEXTO HISTÓRICO (hace {i+1} turnos, solo citas usadas) ==="
                
                if chunks:
                    # Deduplicate and add chunks
                    label_chunks = []
                    for chunk in chunks:
                        add_chunk_if_unique(chunk, label_chunks, source_name)
                    
                    skipped = len(chunks) - len(label_chunks)
                    if label_chunks:
                        step_logger.info(f"[CitationsNode] {source_name}: {len(label_chunks)} unique, {skipped} duplicates skipped")
                        
                        # Format this section
                        entry_citations = citation_engine.create_citations(label_chunks)
                        for j, c in enumerate(entry_citations):
                            c.index = label_chunks[j]["_citation_index"]
                        
                        formatted = citation_engine.format_context_with_citations(entry_citations)
                        
                        if formatted:
                            context_parts.append(label)
                            context_parts.append(formatted)
                            context_parts.append("")  # Empty line separator
                    elif skipped > 0:
                        step_logger.info(f"[CitationsNode] {source_name}: ALL {skipped} chunks were duplicates, skipped entirely")
                        
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                step_logger.warning(f"[CitationsNode] Failed to process context history entry {i}: {e}")
    
    # Add current context chunks (with deduplication)
    current_chunks = state.get("chunks", [])
    if current_chunks:
        label_chunks = []
        for chunk in current_chunks:
            add_chunk_if_unique(chunk, label_chunks, "current")
        
        skipped = len(current_chunks) - len(label_chunks)
        if label_chunks:
            step_logger.info(f"[CitationsNode] current: {len(label_chunks)} unique, {skipped} duplicates skipped")
            
            # Create citations for current
            current_citations = citation_engine.create_citations(label_chunks)
            for j, c in enumerate(current_citations):
                c.index = label_chunks[j]["_citation_index"]
            
            current_context = citation_engine.format_context_with_citations(current_citations)
            
            if current_context:
                if context_parts:  # If we have previous contexts
                    context_parts.append("=== CONTEXTO ACTUAL (nuevo para esta consulta) ===")
                context_parts.append(current_context)
        elif skipped > 0:
            step_logger.info(f"[CitationsNode] current: ALL {skipped} chunks were duplicates, skipped entirely")
    
    # Create unified citations list from all chunks
    all_citations = citation_engine.create_citations(all_chunks)
    # Restore proper indexing
    for i, c in enumerate(all_citations):
        c.index = all_chunks[i].get("_citation_index", i + 1)
    
    context = "\n".join(context_parts)
    
    # Log dedup summary
    step_logger.info(f"[CitationsNode] DEDUP SUMMARY: {dedup_stats['total_chunks_input']} input → {dedup_stats['unique_chunks']} unique ({dedup_stats['duplicates_skipped']} duplicates skipped)")
    if dedup_stats["skipped_article_ids"]:
        step_logger.info(f"[CitationsNode] Skipped article_ids: {dedup_stats['skipped_article_ids'][:10]}{'...' if len(dedup_stats['skipped_article_ids']) > 10 else ''}")
    
    # Phoenix tracing
    if _tracer:
        try:
            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("citations.total_input_chunks", dedup_stats["total_chunks_input"])
                span.set_attribute("citations.unique_chunks", dedup_stats["unique_chunks"])
                span.set_attribute("citations.duplicates_skipped", dedup_stats["duplicates_skipped"])
                span.set_attribute("citations.final_count", len(all_citations))
                span.set_attribute("citations.context_length", len(context))
        except Exception:
            pass  # Ignore tracing errors
    
    step_logger.info(f"[CitationsNode] Created {len(all_citations)} total citations ({len(context)} chars context)")
    return {"citations": all_citations, "context": context}


def generate_node(
    state: ChatGraphState, 
    *,
    llm_provider, 
    prompt_builder
) -> Dict[str, Any]:
    """
    Generate LLM response with context.
    
    Args:
        state: Current workflow state
        llm_provider: LLM provider for generation
        prompt_builder: Builder for system prompts
        
    Returns:
        State update with response and metadata
    """
    step_logger.info(f"[GenerateNode] Building system prompt...")
    # Use provided system prompt from state, or build default one
    system_prompt = state.get("system_prompt") or prompt_builder.build_system_prompt()
    
    step_logger.info(f"[GenerateNode] Generating LLM response...")
    llm_response = llm_provider.generate(
        messages=state["messages"],
        context=state["context"],
        system_prompt=system_prompt
    )
    
    # Build config matrix for beta testing feedback
    # Load config settings
    import yaml
    from pathlib import Path
    version_context = {"next_version_depth": -1, "previous_version_depth": 1}
    max_refs = 3  # Default REFERS_TO expansion depth
    try:
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                version_context = config.get("version_context", version_context)
                max_refs = config.get("retrieval", {}).get("max_refs", 3)
    except Exception:
        pass
    
    config_matrix = {
        "model": llm_provider.model,
        "temperature": getattr(llm_provider, 'temperature', 1.0),
        "top_k": state.get("top_k", 10),
        "collector_type": state.get("context_strategy", "unknown"),
        "prompt_version": "1.0",  # Hardcoded for now, can be made configurable
        "context_reused": state.get("skip_collector", False),
        "next_version_depth": version_context.get("next_version_depth", -1),
        "previous_version_depth": version_context.get("previous_version_depth", 1),
        "max_refers_to": max_refs
    }
    
    step_logger.info(f"[GenerateNode] Generated response ({len(llm_response.content)} chars)")
    return {
        "response": llm_response.content,
        "system_prompt": system_prompt,
        "metadata": {
            "llm_model": llm_provider.model,
            "tokens_used": llm_response.usage,
            "config_matrix": config_matrix
        }
    }


def extract_citations_node(
    state: ChatGraphState, 
    *,
    citation_engine
) -> Dict[str, Any]:
    """
    Extract and re-index used citations from response.
    
    Args:
        state: Current workflow state
        citation_engine: Engine for citation management
        
    Returns:
        State update with cleaned response and used citations
    """
    step_logger.info(f"[ExtractCitationsNode] Extracting citations from response...")
    response_text, used_citations = citation_engine.extract_and_reindex_citations(
        state["response"], state["citations"]
    )
    
    execution_time_ms = (time.time() - state["start_time"]) * 1000
    
    step_logger.info(f"[ExtractCitationsNode] Used {len(used_citations)} citations, completed in {execution_time_ms:.2f}ms")
    return {
        "response": response_text,
        "used_citations": used_citations,
        "execution_time_ms": execution_time_ms
    }
