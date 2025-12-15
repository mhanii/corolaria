"""
Agent-based Context Collector using LangGraph ReAct Agent.

Uses LangGraph's prebuilt create_react_agent for a well-tested
agent loop instead of custom implementation.

Configuration loaded from config/config.yaml and config/prompts.yaml.
Supports multiple LLM providers (Gemini, Azure OpenAI) via langchain_factory.
"""
import os
from typing import List, Dict, Any, Optional

from langgraph.prebuilt import create_react_agent

from src.domain.interfaces.context_collector import ContextCollector, ContextResult
from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.domain.interfaces.graph_adapter import GraphAdapter
from src.ai.agents.tools import create_agent_tools, ContextAccumulator
from src.ai.agents.langchain_factory import create_langchain_llm
from src.config import get_llm_config, get_agent_config, get_prompt
from src.utils.logger import step_logger


# Default prompt if not found in config
DEFAULT_AGENT_PROMPT = """Eres un agente de investigación legal especializado en derecho español. 
Tu tarea es encontrar los artículos legales más relevantes para responder la pregunta del usuario.

INSTRUCCIONES:
1. Usa run_rag_query para buscar artículos por similitud semántica
2. Usa add_to_context para añadir los artículos relevantes al contexto final
3. Cuando tengas 3-7 artículos relevantes, termina tu búsqueda"""


class AgentCollector(ContextCollector):
    """
    Context collector using LangGraph's prebuilt ReAct agent.
    
    Configuration is loaded from config/config.yaml:
    - agent.provider: LLM provider (gemini | azure_openai)
    - agent.max_iterations: Maximum agent loop iterations
    - agent.model: Model/deployment name
    - agent.temperature: Temperature for agent LLM
    
    System prompt loaded from config/prompts.yaml:
    - agent_system_prompt
    """
    
    def __init__(
        self,
        graph_adapter: GraphAdapter,
        embedding_provider: EmbeddingProvider,
        index_name: str = None,
        max_iterations: int = None,
        provider: str = None,
        model_name: str = None,
        temperature: float = None
    ):
        """
        Initialize the agent collector.
        
        All parameters default to values from config/config.yaml if not provided.
        
        Args:
            graph_adapter: Neo4j adapter for graph queries
            embedding_provider: Embeddings for semantic search
            index_name: Vector index name (from config if None)
            max_iterations: Maximum agent loop iterations (from config if None)
            provider: LLM provider - gemini or azure_openai (from config if None)
            model_name: Model/deployment to use (from config if None)
            temperature: LLM temperature (from config if None)
        """
        self._adapter = graph_adapter
        self._embedding_provider = embedding_provider
        
        # Load configuration
        llm_config = get_llm_config()
        agent_config = get_agent_config()
        
        # Use provided values or fall back to config
        self._index_name = index_name or "article_embeddings"
        self._max_iterations = max_iterations or agent_config.get("max_iterations", 5)
        self._provider = provider or agent_config.get("provider") or llm_config.get("provider", "gemini")
        self._model_name = model_name or agent_config.get("model") or llm_config.get("model", "gemini-2.5-flash")
        self._temperature = temperature if temperature is not None else agent_config.get("temperature", 0.3)
        
        # Load system prompt from config
        self._system_prompt = get_prompt("agent_system_prompt", DEFAULT_AGENT_PROMPT)
        
        # Create LLM using factory (supports Gemini and Azure OpenAI)
        self._llm = create_langchain_llm(
            provider=self._provider,
            model=self._model_name,
            temperature=self._temperature
        )
        
        step_logger.info(
            f"[AgentCollector] Initialized with provider={self._provider}, model={self._model_name}, "
            f"temperature={self._temperature}, max_iterations={self._max_iterations}"
        )
    
    @property
    def name(self) -> str:
        """Human-readable name of this collector."""
        return "AgentCollector"
    
    def collect(
        self,
        query: str,
        top_k: int = 10,
        **kwargs
    ) -> ContextResult:
        """
        Collect context using the LangGraph ReAct agent.
        
        Args:
            query: The user's query
            top_k: Hint for max articles (soft limit, agent decides)
            **kwargs: Additional parameters
            
        Returns:
            ContextResult with collected article chunks
        """
        step_logger.info(f"[AgentCollector] Starting collection for: '{query[:50]}...'")
        
        # Create fresh context accumulator for this query
        context_accumulator = ContextAccumulator()
        
        # Create tools with injected dependencies
        tools = create_agent_tools(
            graph_adapter=self._adapter,
            embedding_provider=self._embedding_provider,
            context_accumulator=context_accumulator,
            index_name=self._index_name
        )
        
        # Create ReAct agent using LangGraph prebuilt
        agent = create_react_agent(
            model=self._llm,
            tools=tools,
            prompt=self._system_prompt
        )
        
        # Configure recursion limit (controls max iterations)
        config = {"recursion_limit": self._max_iterations * 2 + 1}
        
        try:
            # Invoke the agent
            result = agent.invoke(
                {"messages": [("user", query)]},
                config=config
            )
            
            # Extract metadata from result
            messages = result.get("messages", [])
            iterations = sum(1 for m in messages if hasattr(m, "tool_calls") and m.tool_calls)
            
            step_logger.info(
                f"[AgentCollector] Collection complete: {iterations} tool calls, "
                f"{len(context_accumulator.chunks)} articles"
            )
            
            return ContextResult(
                chunks=context_accumulator.chunks,
                strategy_name=self.name,
                metadata={
                    "iterations": iterations,
                    "total_messages": len(messages),
                    "max_iterations": self._max_iterations,
                    "model": self._model_name
                }
            )
            
        except Exception as e:
            step_logger.error(f"[AgentCollector] Agent error: {e}", exc_info=True)
            
            # Return whatever context was accumulated before error
            return ContextResult(
                chunks=context_accumulator.chunks,
                strategy_name=self.name,
                metadata={
                    "error": str(e),
                    "partial": True
                }
            )
