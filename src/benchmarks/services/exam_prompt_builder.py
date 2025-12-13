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
2. Presta mucha atención a palabras clave y términos técnicos (ej. "activo" vs "pasivo", "abstracto" vs "concreto", etc.)
3. Utiliza el contexto legal proporcionado para fundamentar tu respuesta.
4. Responde ÚNICAMENTE con la letra de la opción correcta (a, b, c o d).
5. NO incluyas explicaciones, justificaciones, citas ni texto adicional.
6. Tu respuesta debe ser SOLO UNA LETRA MINÚSCULA.

Ejemplo de respuesta correcta: b
Ejemplo de respuesta INCORRECTA: "La respuesta es b porque..."
Ejemplo de respuesta INCORRECTA: "b) El artículo establece..."

Información general:

No todas las leyes tienen la misma importancia. De hecho hay una jerarquía entre ellas bien definida.
Si hay alguna contradicción entre las leyes, la que tiene un nivel más alto en la jerarquía prevalece .

| Nivel | Tipo de norma                         | Características clave                                                                      |
| ----- | ------------------------------------- | ------------------------------------------------------------------------------------------ |
| 1     | Constitución Española                 | Norma suprema; todas las demás deben ajustarse a ella.                                  |
| 2     | Tratados internacionales y Derecho UE | Ratificados y publicados; directamente aplicables si proceden de la UE.             |
| 3     | Leyes orgánicas                       | Requieren mayoría absoluta; regulan derechos fundamentales y Estatutos de Autonomía. |
| 4     | Leyes ordinarias                      | Aprobadas por mayoría simple por Cortes Generales o asambleas autonómicas.          |
| 5     | Normas con rango de ley               | Decretos-leyes y decretos legislativos del Gobierno.                    |

Normas reglamentarias y complementarias:

Reglamentos gubernamentales (reales decretos, órdenes ministeriales), que desarrollan las leyes pero no las contradicen.
Normativa autonómica y local (leyes autonómicas, ordenanzas municipales), subordinada a la estatal en competencias compartidas.
Costumbre y principios generales del Derecho, aplicables solo si no hay ley (artículo 1 Código Civil).
"""

    CONTEXT_TEMPLATE = "[Contexto {index}] {normativa_title} - Artículo {article_number}"
    CONTEXT_TEMPLATE_WITH_PATH = "[Contexto {index}] {normativa_title} - Artículo {article_number} ({article_path})"

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
            article_number = chunk.get("article_number", "")
            article_path = chunk.get("article_path") or chunk.get("metadata", {}).get("context_path_text", "")
            normativa_title = chunk.get("normativa_title", "Normativa")
            article_text = chunk.get("article_text", chunk.get("full_text", ""))
            
            # Build header based on available info
            if article_path and article_number:
                # Full format with path in parentheses
                header = self.CONTEXT_TEMPLATE_WITH_PATH.format(
                    index=i,
                    normativa_title=normativa_title,
                    article_number=article_number,
                    article_path=article_path
                )
            elif article_number:
                # Just article number, no path
                header = self.CONTEXT_TEMPLATE.format(
                    index=i,
                    normativa_title=normativa_title,
                    article_number=article_number
                )
            else:
                # Fallback: use path if no article number
                header = f"[Contexto {i}] {normativa_title} - {article_path}"
            
            entry = f"{header}\n{article_text}"
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
