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
from src.benchmarks.services.exam_prompt_builder import ExamPromptBuilder
from src.domain.interfaces.llm_provider import LLMProvider, Message
from src.domain.interfaces.context_collector import ContextCollector
from src.utils.logger import step_logger
from src.observability.benchmark_tracing import (
    BenchmarkSessionTracer,
    trace_question
)


class BenchmarkRunner:
    """
    Runs benchmark exams against an LLM (optionally with RAG context).
    
    Can operate in two modes:
    - Direct LLM: Just questions to the LLM, no RAG context.
    - With RAG: Uses context_collector to retrieve relevant articles.
                By default embeds ONLY the question text (not options).
                Use embed_options=True to include options in embedding query.
                Use multi_query=True to embed question + each option separately.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        context_collector: Optional[ContextCollector] = None,
        use_rag: bool = True,
        embed_options: bool = False,
        multi_query: bool = False,
    ):
        """
        Initialize the benchmark runner.
        
        Args:
            llm_provider: The LLM provider for queries.
            context_collector: Optional context collector for RAG-based queries.
            use_rag: Whether to use RAG context (requires context_collector).
            embed_options: If True, include answer options in embedding query.
                          If False (default), embed only the question text.
            multi_query: If True, embed question + each option separately,
                        retrieve chunks for each, and deduplicate results.
        """
        self.llm_provider = llm_provider
        self.context_collector = context_collector
        self.use_rag = use_rag and context_collector is not None
        self.embed_options = embed_options
        self.multi_query = multi_query
        self.prompt_builder = ExamPromptBuilder()
        
        if use_rag and not context_collector:
            step_logger.warning("[BenchmarkRunner] use_rag=True but no context_collector provided. Falling back to direct LLM.")
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
        
        # Wrap entire exam in a traced session
        with BenchmarkSessionTracer(
            exam_name=exam.name,
            model_name=model_name or "unknown",
            use_rag=self.use_rag,
            parameters=params
        ) as session:
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
            
            # Record final results in the trace
            session.set_final_results(
                correct=correct_count,
                incorrect=incorrect_count,
                unanswered=unanswered_count + error_count,
                total=len(exam.questions),
                score_percent=result.score,
                execution_time_ms=execution_time_ms
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
        # Build the formatted question with options
        question_prompt = self._format_question_prompt(question)
        
        # Trace the question execution
        with trace_question(
            question_id=question.id,
            question_text=question.text
        ) as span:
            if self.use_rag:
                # Choose what to embed based on multi_query and embed_options flags
                if self.multi_query:
                    # Multi-query mode: embed question + each option separately
                    raw_response = self._query_with_multi_rag(question, question_prompt, params)
                elif self.embed_options:
                    # Include full formatted prompt with options
                    query_for_rag = question_prompt
                    raw_response = self._query_with_rag(query_for_rag, question_prompt, params)
                else:
                    # Default: only the question text (more focused embedding)
                    query_for_rag = question.text
                    raw_response = self._query_with_rag(query_for_rag, question_prompt, params)
            else:
                raw_response = self._query_direct(question_prompt)
            
            # Parse the model's answer
            model_answer = self._extract_answer(raw_response)
            
            # Determine correctness
            is_correct = None
            if question.correct_answer and model_answer:
                is_correct = model_answer.lower() == question.correct_answer.lower()
            
            # Record result in the trace (flags incorrect as ERROR)
            span.set_result(
                model_answer=model_answer,
                correct_answer=question.correct_answer,
                is_correct=is_correct,
                raw_response=raw_response
            )
        
        return QuestionResult(
            question_id=question.id,
            model_answer=model_answer,
            correct_answer=question.correct_answer,
            is_correct=is_correct,
            raw_response=raw_response,
        )

    def _format_question_prompt(self, question: Question) -> str:
        """Format a question into a prompt string with options."""
        lines = [question.text, ""]
        
        for letter in sorted(question.options.keys()):
            lines.append(f"{letter}) {question.options[letter]}")
        
        return "\n".join(lines)

    def _query_direct(self, prompt: str) -> str:
        """Query the LLM directly without RAG context."""
        messages = [
            Message(role="user", content=prompt),
        ]
        
        response = self.llm_provider.generate(
            messages,
            system_prompt=self.prompt_builder.build_system_prompt()
        )
        return response.content

    def _query_with_rag(self, query_for_rag: str, formatted_question: str, params: Dict[str, Any]) -> str:
        """
        Query using RAG context collection.
        
        Args:
            query_for_rag: Clean question text to use for embedding/retrieval
            formatted_question: Full formatted question with options for LLM
            params: Parameters including top_k
        """
        top_k = params.get("top_k", 5)
        
        # Step 1: Collect context using ONLY the clean question text
        # This ensures we embed the semantic question, not the exam format/options
        step_logger.info(f"[BenchmarkRunner] Collecting context for: '{query_for_rag[:80]}...'")
        context_result = self.context_collector.collect(
            query=query_for_rag,
            top_k=top_k
        )
        
        # Step 2: Build context string using ExamPromptBuilder
        context_str = self.prompt_builder.build_context(context_result.chunks)
        step_logger.info(f"[BenchmarkRunner] Retrieved {len(context_result.chunks)} chunks for question")
        
        # Step 3: Build the full user message with context + question
        if context_str:
            full_prompt = f"""CONTEXTO LEGAL RELEVANTE:
{context_str}

---

{formatted_question}"""
        else:
            full_prompt = formatted_question
        
        # Step 4: Send to LLM with ExamPromptBuilder's system prompt
        messages = [
            Message(role="user", content=full_prompt),
        ]
        
        response = self.llm_provider.generate(
            messages,
            system_prompt=self.prompt_builder.build_system_prompt()
        )
        return response.content

    def _query_with_multi_rag(self, question: Question, formatted_question: str, params: Dict[str, Any]) -> str:
        """
        Query using multi-query RAG: embed question + each option separately.
        
        Args:
            question: The Question object with text and options
            formatted_question: Full formatted question with options for LLM
            params: Parameters including top_k
        """
        chunks_per_query = params.get("chunks_per_query", 5)
        
        # Build queries: question text + each option
        queries = [question.text]
        for letter in sorted(question.options.keys()):
            queries.append(question.options[letter])
        
        step_logger.info(f"[BenchmarkRunner] Multi-query mode: {len(queries)} queries (question + {len(queries)-1} options)")
        
        # Collect chunks from all queries
        all_chunks: Dict[str, Dict[str, Any]] = {}  # article_id -> chunk (keep highest score)
        
        for i, query_text in enumerate(queries):
            query_label = "question" if i == 0 else f"option_{chr(ord('a') + i - 1)}"
            step_logger.info(f"[BenchmarkRunner] Collecting context for {query_label}: '{query_text[:50]}...'")
            
            context_result = self.context_collector.collect(
                query=query_text,
                top_k=chunks_per_query
            )
            
            # Deduplicate: keep chunk with highest score for each article_id
            for chunk in context_result.chunks:
                article_id = chunk.get("article_id", chunk.get("id", id(chunk)))
                existing = all_chunks.get(article_id)
                if existing is None or chunk.get("score", 0) > existing.get("score", 0):
                    all_chunks[article_id] = chunk
        
        # Sort by score descending and take top results
        final_chunks = sorted(
            all_chunks.values(),
            key=lambda c: c.get("score", 0),
            reverse=True
        )
        
        step_logger.info(f"[BenchmarkRunner] Multi-query retrieved {len(final_chunks)} unique chunks (deduplicated)")
        
        # Build context string using ExamPromptBuilder
        context_str = self.prompt_builder.build_context(final_chunks)
        
        # Build the full user message with context + question
        if context_str:
            full_prompt = f"""CONTEXTO LEGAL RELEVANTE:
{context_str}

---

{formatted_question}"""
        else:
            full_prompt = formatted_question
        
        # Send to LLM with ExamPromptBuilder's system prompt
        messages = [
            Message(role="user", content=full_prompt),
        ]
        
        response = self.llm_provider.generate(
            messages,
            system_prompt=self.prompt_builder.build_system_prompt()
        )
        return response.content

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
