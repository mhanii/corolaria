"""
LangGraph State Definition.
Defines the state schema for the chat workflow.
"""
from typing import TypedDict, List, Dict, Any, Optional
from src.domain.models.citation import Citation
from src.domain.interfaces.llm_provider import Message


class ChatGraphState(TypedDict):
    """
    State for LangGraph chat workflow.
    
    This state flows through each node in the workflow graph,
    accumulating results from each step.
    """
    # Input
    query: str
    conversation_id: Optional[str]
    top_k: int
    
    # Context decision
    previous_context: Optional[str]  # Immediate previous context (for backward compat)
    context_history: List[Dict[str, Any]]  # Full history: [{context_json, citations, is_immediate}]
    skip_collector: bool  # Whether to skip RAG and reuse previous context
    
    # Context collection (from any ContextCollector strategy)
    chunks: List[Dict[str, Any]]
    context_strategy: str  # Name of the context collector strategy used
    
    # Citations
    citations: List[Citation]
    context: str
    
    # LLM
    messages: List[Message]
    system_prompt: str
    
    # Output
    response: str
    used_citations: List[Citation]
    context_json: Optional[str]  # Serialized context for storage
    
    # Metadata
    start_time: float
    execution_time_ms: float
    metadata: Dict[str, Any]

