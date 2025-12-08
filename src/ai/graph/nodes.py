"""
LangGraph Nodes for Chat Workflow.
Each node represents a step in the RAG pipeline.
"""
import time
from typing import Dict, Any

from src.ai.graph.state import ChatGraphState
from src.domain.interfaces.llm_provider import Message
from src.utils.logger import step_logger


def collect_context_node(
    state: ChatGraphState, 
    *, 
    context_collector
) -> Dict[str, Any]:
    """
    Collect context using the configured ContextCollector strategy.
    
    This node is the entry point for context gathering in the workflow.
    It delegates to the injected ContextCollector, enabling pluggable
    strategies (RAG, graph traversal, hybrid, voyager agents, etc.).
    
    Args:
        state: Current workflow state
        context_collector: ContextCollector implementation to use
        
    Returns:
        State update with collected chunks and strategy name
    """
    step_logger.info(f"[CollectContextNode] Collecting context using {context_collector.name}...")
    
    result = context_collector.collect(
        query=state["query"],
        top_k=state["top_k"]
    )
    
    step_logger.info(f"[CollectContextNode] Collected {len(result)} chunks via {result.strategy_name}")
    
    return {
        "chunks": result.chunks,
        "context_strategy": result.strategy_name
    }


def build_citations_node(
    state: ChatGraphState, 
    *,
    citation_engine
) -> Dict[str, Any]:
    """
    Create citations from chunks and format context.
    
    Args:
        state: Current workflow state
        citation_engine: Engine for citation management
        
    Returns:
        State update with citations and formatted context
    """
    step_logger.info(f"[CitationsNode] Creating citations from {len(state['chunks'])} chunks...")
    citations = citation_engine.create_citations(state["chunks"])
    
    step_logger.info(f"[CitationsNode] Formatting context with citations...")
    context = citation_engine.format_context_with_citations(citations)
    
    step_logger.info(f"[CitationsNode] Created {len(citations)} citations ({len(context)} chars context)")
    return {"citations": citations, "context": context}


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
    
    step_logger.info(f"[GenerateNode] Generated response ({len(llm_response.content)} chars)")
    return {
        "response": llm_response.content,
        "system_prompt": system_prompt,
        "metadata": {
            "llm_model": llm_provider.model,
            "tokens_used": llm_response.usage
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
