"""
Exam-specific Prompt Builder.
Builds prompts optimized for multiple-choice exam answering without citations.
"""
from typing import List, Optional, Dict, Any


class ExamPromptBuilder:
    """
    Builds prompts for exam/benchmark scenarios.
    
    Unlike the standard PromptBuilder, this:
    - Does NOT request citations
    - Focuses on selecting the correct answer
    - Instructs the model to respond with only the letter
    
    Implements the same interface as PromptBuilder for compatibility.
    """
    
    SYSTEM_PROMPT = """Eres un experto jurídico español realizando un examen de oposiciones.

INSTRUCCIONES CRÍTICAS:
1. Analiza la pregunta y todas las opciones cuidadosamente.
2. Utiliza el contexto legal proporcionado para fundamentar tu respuesta.
3. Responde ÚNICAMENTE con la letra de la opción correcta (a, b, c o d).
4. NO incluyas explicaciones, justificaciones, citas ni texto adicional.
5. Tu respuesta debe ser SOLO UNA LETRA MINÚSCULA.

Ejemplo de respuesta correcta: b
Ejemplo de respuesta INCORRECTA: "La respuesta es b porque..."
Ejemplo de respuesta INCORRECTA: "b) El artículo establece..."
"""

    CONTEXT_TEMPLATE = "[Contexto {index}] {normativa_title} - {article_path}\n{article_text}"

    def __init__(self, config_path: Optional[str] = None):
        """Initialize ExamPromptBuilder. config_path is ignored (for interface compatibility)."""
        pass  # No configuration needed for exam mode

    def build_system_prompt(self) -> str:
        """
        Get the system prompt for exam mode.
        
        Returns:
            System prompt string.
        """
        return self.SYSTEM_PROMPT

    def build_context(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Build context string from retrieved chunks (without citation instruction).
        
        Args:
            chunks: List of article chunks from RAG retrieval.
            
        Returns:
            Formatted context string.
        """
        if not chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            article_path = chunk.get("article_path") or chunk.get("metadata", {}).get("context_path_text", "")
            
            entry = self.CONTEXT_TEMPLATE.format(
                index=i,
                normativa_title=chunk.get("normativa_title", "Normativa"),
                article_path=article_path or chunk.get("article_number", ""),
                article_text=chunk.get("article_text", chunk.get("full_text", ""))
            )
            context_parts.append(entry)
        
        # No citation instruction for exam mode
        return "\n\n".join(context_parts)

    def build_user_message(self, query: str) -> str:
        """
        Build user message (passthrough).
        
        Args:
            query: User's question/exam question.
            
        Returns:
            The query as-is.
        """
        return query

    def get_few_shot_example(self) -> Optional[Dict[str, str]]:
        """
        Get few-shot example (none for exam mode).
        
        Returns:
            None (no few-shot examples needed).
        """
        return None


# Export for compatibility with PromptBuilder interface
__all__ = ["ExamPromptBuilder"]
