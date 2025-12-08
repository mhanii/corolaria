"""
Benchmark Runner Service.
Runs exams through the RAG pipeline or directly to an LLM and scores results.
"""
import re
import time
import uuid
from typing import Optional, List, Dict, Any

from src.benchmarks.domain.schemas import (
    Exam,
    Question,
    BenchmarkRun,
    BenchmarkResult,
    QuestionResult,
)
from src.domain.interfaces.llm_provider import LLMProvider, Message
from src.utils.logger import step_logger


# Exam-specific system prompt that instructs single-letter answers
EXAM_SYSTEM_PROMPT = """Eres un experto jurídico que está realizando un examen oficial de oposiciones.

INSTRUCCIONES CRÍTICAS:
1. Lee la pregunta y las opciones cuidadosamente.
2. Responde ÚNICAMENTE con la letra de la opción correcta (a, b, c o d).
3. NO incluyas explicaciones, justificaciones ni texto adicional.
4. Tu respuesta debe ser SOLO UNA LETRA.

Ejemplo de respuesta correcta: "b"
Ejemplo de respuesta INCORRECTA: "La respuesta es b porque..."
"""


class BenchmarkRunner:
    """
    Runs benchmark exams against an LLM (optionally with RAG context).
    
    Can operate in two modes:
    - Direct LLM: Just questions to the LLM, no RAG context.
    - With RAG: Uses the existing RAG pipeline to provide context.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        chat_service: Optional[Any] = None,  # LangGraphChatService or ChatService
        use_rag: bool = True,
    ):
        """
        Initialize the benchmark runner.
        
        Args:
            llm_provider: The LLM provider for direct queries.
            chat_service: Optional chat service for RAG-based queries.
            use_rag: Whether to use RAG context (requires chat_service).
        """
        self.llm_provider = llm_provider
        self.chat_service = chat_service
        self.use_rag = use_rag and chat_service is not None
        
        if use_rag and not chat_service:
            step_logger.warning("[BenchmarkRunner] use_rag=True but no chat_service provided. Falling back to direct LLM.")
            self.use_rag = False

    def run_exam(
        self,
        exam: Exam,
        model_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> BenchmarkResult:
        """
        Run a full exam and return aggregated results.
        
        Args:
            exam: The Exam object to run.
            model_name: Optional model name override.
            parameters: Optional parameters for the run (e.g., top_k).
            
        Returns:
            BenchmarkResult with all question results and scores.
        """
        start_time = time.time()
        params = parameters or {}
        
        run = BenchmarkRun(
            run_id=str(uuid.uuid4()),
            exam_name=exam.name,
            model_name=model_name or "unknown",
            use_rag=self.use_rag,
            parameters=params,
        )
        
        step_logger.info(f"[BenchmarkRunner] Starting exam: {exam.name} ({len(exam.questions)} questions)")
        
        results: List[QuestionResult] = []
        correct_count = 0
        incorrect_count = 0
        unanswered_count = 0
        error_count = 0
        
        for question in exam.questions:
            try:
                q_result = self._run_question_with_retry(question, params, max_retries=3)
                results.append(q_result)
                
                if q_result.is_correct is None:
                    unanswered_count += 1
                elif q_result.is_correct:
                    correct_count += 1
                else:
                    incorrect_count += 1
                
                step_logger.info(
                    f"  Q{question.id}: model={q_result.model_answer}, "
                    f"correct={q_result.correct_answer}, is_correct={q_result.is_correct}"
                )
            except Exception as e:
                # Log error but continue with remaining questions
                step_logger.error(f"  Q{question.id}: FAILED - {type(e).__name__}: {e}")
                error_count += 1
                results.append(QuestionResult(
                    question_id=question.id,
                    model_answer=None,
                    correct_answer=question.correct_answer,
                    is_correct=None,
                    raw_response=f"ERROR: {e}",
                ))
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        result = BenchmarkResult(
            run=run,
            results=results,
            total_questions=len(exam.questions),
            correct_count=correct_count,
            incorrect_count=incorrect_count,
            unanswered_count=unanswered_count + error_count,
            execution_time_ms=execution_time_ms,
        )
        
        step_logger.info(
            f"[BenchmarkRunner] Exam complete. Score: {result.score:.1f}% "
            f"({correct_count}/{len(exam.questions) - unanswered_count - error_count})"
            + (f" [Errors: {error_count}]" if error_count else "")
        )
        
        return result

    def _run_question_with_retry(
        self,
        question: Question,
        params: Dict[str, Any],
        max_retries: int = 3,
    ) -> QuestionResult:
        """
        Run a question with retry logic for transient network errors.
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return self._run_question(question, params)
            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                
                # Check if it's a retryable error (network, timeout, etc.)
                retryable_errors = ('ConnectError', 'TimeoutError', 'ConnectionError', 
                                    'ReadTimeout', 'ConnectTimeout', 'httpcore.ConnectError')
                if any(err in str(type(e).__mro__) or err in error_type for err in retryable_errors):
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    step_logger.warning(
                        f"  Q{question.id}: Retry {attempt + 1}/{max_retries} after {error_type}, "
                        f"waiting {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    # Non-retryable error, raise immediately
                    raise
        
        # All retries failed
        raise last_error

    def _run_question(
        self,
        question: Question,
        params: Dict[str, Any],
    ) -> QuestionResult:
        """
        Run a single question through the LLM.
        
        Args:
            question: The Question to ask.
            params: Parameters for the query.
            
        Returns:
            QuestionResult with model answer and correctness.
        """
        # Build the question prompt
        question_prompt = self._format_question_prompt(question)
        
        if self.use_rag:
            raw_response = self._query_with_rag(question_prompt, params)
        else:
            raw_response = self._query_direct(question_prompt)
        
        # Parse the model's answer
        model_answer = self._extract_answer(raw_response)
        
        # Determine correctness
        is_correct = None
        if question.correct_answer and model_answer:
            is_correct = model_answer.lower() == question.correct_answer.lower()
        
        return QuestionResult(
            question_id=question.id,
            model_answer=model_answer,
            correct_answer=question.correct_answer,
            is_correct=is_correct,
            raw_response=raw_response,
        )

    def _format_question_prompt(self, question: Question) -> str:
        """Format a question into a prompt string."""
        lines = [f"Pregunta {question.id}: {question.text}", ""]
        
        for letter in sorted(question.options.keys()):
            lines.append(f"{letter}) {question.options[letter]}")
        
        return "\n".join(lines)

    def _query_direct(self, prompt: str) -> str:
        """Query the LLM directly without RAG context."""
        messages = [
            Message(role="system", content=EXAM_SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ]
        
        response = self.llm_provider.generate(messages)
        return response.content

    def _query_with_rag(self, prompt: str, params: Dict[str, Any]) -> str:
        """Query using the RAG pipeline (chat service)."""
        # Prepend the exam instruction to the prompt
        full_prompt = (
            "IMPORTANTE: Responde ÚNICAMENTE con una letra (a, b, c o d). "
            "No incluyas explicaciones.\n\n" + prompt
        )
        
        top_k = params.get("top_k", 5)
        
        # Use the chat service which internally uses RAG
        response = self.chat_service.chat(
            query=full_prompt,
            conversation_id=None,  # Each question is independent
            top_k=top_k,
        )
        
        return response.response

    def _extract_answer(self, raw_response: str) -> Optional[str]:
        """
        Extract the answer letter from the model's response.
        
        Tries multiple patterns to be robust:
        1. Single letter response
        2. Letter at start or end
        3. Letter in parentheses or with punctuation
        """
        if not raw_response:
            return None
        
        text = raw_response.strip().lower()
        
        # Pattern 1: Just a single letter
        if len(text) == 1 and text in "abcd":
            return text
        
        # Pattern 2: Letter at the very start
        if text and text[0] in "abcd":
            # Check if it's followed by non-letter or nothing
            if len(text) == 1 or not text[1].isalpha():
                return text[0]
        
        # Pattern 3: Common patterns like "a)", "a.", "(a)", "Respuesta: a"
        patterns = [
            r"^([abcd])\s*[\)\.\:]",        # a) or a. or a:
            r"^\(([abcd])\)",                # (a)
            r"respuesta\s*:?\s*([abcd])",    # respuesta: a
            r"opción\s*:?\s*([abcd])",       # opción: a
            r"^la\s+([abcd])\b",             # la a
            r"\b([abcd])\s*$",               # ends with a letter
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).lower()
        
        # Pattern 4: First letter found in response
        for char in text:
            if char in "abcd":
                return char
        
        return None
