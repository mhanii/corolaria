"""
Context Decision System.
Determines whether to run the context collector (RAG) or reuse previous context.
"""
import re
from dataclasses import dataclass
from typing import Optional, List

from src.domain.models.conversation import Conversation
from src.utils.logger import step_logger

# Import tracer for Phoenix observability
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("context_decision")
except ImportError:
    _tracer = None


# Configuration
MAX_SHORT_QUERY_WORDS = 6  # Queries longer than this always run collector
SIMILARITY_THRESHOLD = 0.85  # High threshold for matching clarification patterns

# Legal keywords that indicate need for context collector
LEGAL_KEYWORDS = [
    "artículo", "articulo", "art.",
    "ley", "leyes",
    "normativa", "normativo",
    "código", "codigo",
    "reglamento",
    "decreto",
    "constitución", "constitucion",
    "sentencia",
    "jurisprudencia",
    "tribunal",
    "juzgado",
    "demanda",
    "recurso",
    "apelación", "apelacion",
    "casación", "casacion",
    "amparo",
    "habeas corpus",
    "real decreto",
    "orden ministerial",
    "disposición", "disposicion",
    "transitoria",
    "derogatoria",
]

# Simple regex patterns for obvious clarifications
CLARIFICATION_PATTERNS = [
    r"^\s*¿?(estás?|estas?) seguro\??$",
    r"^\s*¿?seguro\??$",
    r"^\s*¿?de verdad\??$",
    r"^\s*¿?en serio\??$",
    r"^\s*¿?por qué\??$",
    r"^\s*¿?cómo\??$",
    r"^\s*ok$",
    r"^\s*vale$",
    r"^\s*entiendo$",
    r"^\s*ya veo$",
]


@dataclass
class DecisionResult:
    """Result of context decision check."""
    needs_collector: bool
    reason: str
    confidence: float = 1.0
    similarity_score: Optional[float] = None
    
    def __repr__(self) -> str:
        return f"DecisionResult(needs_collector={self.needs_collector}, reason='{self.reason}')"


class ContextDecision:
    """
    Determines whether to run the context collector or reuse previous context.
    
    Decision flow:
    1. Check message length - long queries always need collector
    2. Check for legal keywords - if present, need collector
    3. Check pattern matching against ChromaDB classification embeddings
    4. Check if previous context exists
    
    This class is traced by Phoenix for observability.
    """
    
    def __init__(
        self,
        chroma_store=None,
        max_short_query_words: int = MAX_SHORT_QUERY_WORDS,
        similarity_threshold: float = SIMILARITY_THRESHOLD
    ):
        """
        Initialize context decision system.
        
        Args:
            chroma_store: ChromaClassificationStore for embedding similarity
            max_short_query_words: Max words for a query to be considered "short"
            similarity_threshold: Threshold for matching clarification patterns
        """
        self._chroma_store = chroma_store
        self._max_short_words = max_short_query_words
        self._similarity_threshold = similarity_threshold
        
        step_logger.info(
            f"[ContextDecision] Initialized with max_words={max_short_query_words}, "
            f"threshold={similarity_threshold}"
        )
    
    def set_chroma_store(self, store):
        """Set the ChromaDB store after initialization."""
        self._chroma_store = store
    
    def needs_context_collector(
        self,
        query: str,
        conversation: Conversation,
        previous_context: Optional[str] = None
    ) -> DecisionResult:
        """
        Determine if the context collector should be run.
        
        Args:
            query: The user's current query
            conversation: Current conversation with history
            previous_context: Previously used context (if any)
            
        Returns:
            DecisionResult indicating whether to run collector and why
        """
        if _tracer:
            with _tracer.start_as_current_span("ContextDecision.needs_context_collector") as span:
                span.set_attribute("input.query", query)
                span.set_attribute("input.query_length_words", len(query.split()))
                span.set_attribute("input.has_previous_context", previous_context is not None)
                span.set_attribute("input.conversation_message_count", len(conversation.messages))
                
                result = self._evaluate(query, conversation, previous_context)
                
                span.set_attribute("output.needs_collector", result.needs_collector)
                span.set_attribute("output.reason", result.reason)
                span.set_attribute("output.confidence", result.confidence)
                if result.similarity_score is not None:
                    span.set_attribute("output.similarity_score", result.similarity_score)
                
                return result
        else:
            return self._evaluate(query, conversation, previous_context)
    
    def _evaluate(
        self,
        query: str,
        conversation: Conversation,
        previous_context: Optional[str]
    ) -> DecisionResult:
        """Internal evaluation logic."""
        query_lower = query.lower().strip()
        words = query_lower.split()
        word_count = len(words)
        
        # Step 1: Check message length - long queries always need collector
        if word_count > self._max_short_words:
            step_logger.info(f"[ContextDecision] Query too long ({word_count} words), needs collector")
            return DecisionResult(
                needs_collector=True,
                reason="query_too_long",
                confidence=1.0
            )
        
        # Step 2: Check for legal keywords - if present, need collector
        if self._has_legal_keywords(query_lower):
            step_logger.info(f"[ContextDecision] Query contains legal terms, needs collector")
            return DecisionResult(
                needs_collector=True,
                reason="contains_legal_terms",
                confidence=1.0
            )
        
        # Step 3: Check pattern matching (fast regex patterns)
        if self._matches_clarification_pattern(query_lower):
            # Check if we have previous context to reuse
            if not previous_context:
                step_logger.info(f"[ContextDecision] Pattern match but no previous context")
                return DecisionResult(
                    needs_collector=True,
                    reason="no_previous_context",
                    confidence=0.8
                )
            
            step_logger.info(f"[ContextDecision] Matches clarification pattern, skip collector")
            return DecisionResult(
                needs_collector=False,
                reason="matches_clarification_pattern",
                confidence=0.95
            )
        
        # Step 4: Check embedding similarity against ChromaDB
        if self._chroma_store:
            similarity_result = self._check_embedding_similarity(query)
            if similarity_result:
                similarity = similarity_result.get("similarity", 0)
                if similarity >= self._similarity_threshold:
                    if not previous_context:
                        step_logger.info(f"[ContextDecision] High similarity but no previous context")
                        return DecisionResult(
                            needs_collector=True,
                            reason="no_previous_context",
                            confidence=0.8,
                            similarity_score=similarity
                        )
                    
                    step_logger.info(
                        f"[ContextDecision] High similarity ({similarity:.2f}) to "
                        f"'{similarity_result.get('phrase', '')}', skip collector"
                    )
                    return DecisionResult(
                        needs_collector=False,
                        reason="high_embedding_similarity",
                        confidence=similarity,
                        similarity_score=similarity
                    )
        
        # Step 5: Must have previous context to skip
        if not previous_context:
            step_logger.info(f"[ContextDecision] No previous context, needs collector")
            return DecisionResult(
                needs_collector=True,
                reason="no_previous_context",
                confidence=1.0
            )
        
        # Default: run collector for safety
        step_logger.info(f"[ContextDecision] Default: needs collector")
        return DecisionResult(
            needs_collector=True,
            reason="default",
            confidence=0.7
        )
    
    def _has_legal_keywords(self, query_lower: str) -> bool:
        """Check if query contains legal keywords."""
        for keyword in LEGAL_KEYWORDS:
            # Use word boundaries to avoid partial matches
            pattern = rf"\b{re.escape(keyword)}\b"
            if re.search(pattern, query_lower):
                return True
        return False
    
    def _matches_clarification_pattern(self, query_lower: str) -> bool:
        """Check if query matches known clarification patterns."""
        for pattern in CLARIFICATION_PATTERNS:
            if re.match(pattern, query_lower, re.IGNORECASE):
                return True
        return False
    
    def _check_embedding_similarity(self, query: str) -> Optional[dict]:
        """
        Check similarity against classification embeddings.
        
        Returns the best matching result if above a minimum threshold.
        """
        if not self._chroma_store:
            return None
        
        try:
            matches = self._chroma_store.find_similar(
                query=query,
                top_k=1,
                category="clarification"
            )
            if matches and matches[0]["similarity"] > 0.5:  # Minimum to consider
                return matches[0]
        except Exception as e:
            step_logger.warning(f"[ContextDecision] Embedding check failed: {e}")
        
        return None
