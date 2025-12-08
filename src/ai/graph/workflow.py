"""
LangGraph Workflow for Chat with RAG.
Builds and compiles the StateGraph for chat processing.
"""
from functools import partial
from typing import Optional
from langgraph.graph import StateGraph, END

from src.ai.graph.state import ChatGraphState
from src.ai.graph import nodes
from src.utils.logger import step_logger


def build_chat_workflow(
    context_collector,
    llm_provider,
    citation_engine,
    prompt_builder,
    checkpointer=None
):
    """
    Build the chat workflow graph.
    
    Flow: collect_context → build_citations → generate → extract_citations → END
    
    Args:
        context_collector: ContextCollector for gathering context (RAG, graph, etc.)
        llm_provider: LLM provider for generation
        citation_engine: Engine for citation management
        prompt_builder: Builder for prompts
        checkpointer: Optional SQLite checkpointer for state persistence
        
    Returns:
        Compiled LangGraph workflow
    """
    step_logger.info("[Workflow] Building chat workflow graph...")
    
    # Create graph with state schema
    workflow = StateGraph(ChatGraphState)
    
    # Add nodes with bound dependencies
    # Each node function receives state and its required dependencies
    
    workflow.add_node(
        "collect_context",
        partial(
            nodes.collect_context_node,
            context_collector=context_collector
        )
    )
    
    workflow.add_node(
        "build_citations",
        partial(
            nodes.build_citations_node,
            citation_engine=citation_engine
        )
    )
    
    workflow.add_node(
        "generate",
        partial(
            nodes.generate_node,
            llm_provider=llm_provider,
            prompt_builder=prompt_builder
        )
    )
    
    workflow.add_node(
        "extract_citations",
        partial(
            nodes.extract_citations_node,
            citation_engine=citation_engine
        )
    )
    
    # Define edges (linear flow for now, can add conditional routing later)
    workflow.set_entry_point("collect_context")
    workflow.add_edge("collect_context", "build_citations")
    workflow.add_edge("build_citations", "generate")
    workflow.add_edge("generate", "extract_citations")
    workflow.add_edge("extract_citations", END)
    
    # Compile the graph with optional checkpointer
    if checkpointer:
        step_logger.info("[Workflow] Compiling with SQLite checkpointer for state persistence")
        compiled = workflow.compile(checkpointer=checkpointer)
    else:
        compiled = workflow.compile()
    
    step_logger.info("[Workflow] Chat workflow compiled successfully")
    return compiled
