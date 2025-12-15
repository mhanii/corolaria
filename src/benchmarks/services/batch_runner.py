"""
Batch Benchmark Runner Service.
Handles preparing and submitting exams as batch jobs to Google Gemini.
"""
import json
import time
import os
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.benchmarks.domain.schemas import Exam, Question
from src.benchmarks.services.exam_prompt_builder import ExamPromptBuilder
from src.domain.interfaces.context_collector import ContextCollector
from src.ai.llm.gemini_provider import GeminiLLMProvider
from src.utils.logger import step_logger


class BatchBenchmarkRunner:
    """
    Runs benchmark exams using Gemini's Batch API for cost efficiency and scale.
    
    Workflow:
    1. prepare_batch_file: Generates prompts (with RAG) for all questions and saves to JSONL.
    2. submit_batch: Uploads the file and submits the batch job.
    3. get_status: Checks job status.
    4. process_results: Retrieves and parses results (once job is COMPLETED).
    """

    def __init__(
        self,
        llm_provider: GeminiLLMProvider,
        context_collector: Optional[ContextCollector] = None,
        max_threads: int = 10 
    ):
        self.llm_provider = llm_provider
        self.context_collector = context_collector
        self.prompt_builder = ExamPromptBuilder()
        self.max_threads = max_threads

    def prepare_batch_file(
        self,
        exam: Exam,
        output_path: str,
        use_rag: bool = True,
        top_k: int = 5
    ) -> int:
        """
        Prepare the JSONL file for batch processing.
        
        Args:
            exam: The exam to process.
            output_path: Local path to save the JSONL file.
            use_rag: Whether to use RAG context.
            
        Returns:
            Number of requests written.
        """
        step_logger.info(f"[BatchRunner] Preparing batch file for exam: {exam.name} ({len(exam.questions)} questions)")
        
        # Determine RAG usage
        actual_use_rag = use_rag and self.context_collector is not None
        if use_rag and not self.context_collector:
            step_logger.warning("[BatchRunner] use_rag=True but no context_collector. Falling back to direct LLM.")
            actual_use_rag = False

        requests = []
        
        # Use ThreadPoolExecutor for parallel context collection if RAG is enabled
        with ThreadPoolExecutor(max_workers=self.max_threads if actual_use_rag else 1) as executor:
            future_to_question = {
                executor.submit(self._build_prompt_for_question, q, actual_use_rag, top_k): q 
                for q in exam.questions
            }
            
            for future in as_completed(future_to_question):
                question = future_to_question[future]
                try:
                    full_prompt = future.result()
                    
                    # Create batch request entry
                    # Format for google.genai SDK (passed to file API?)
                    # Typically for batch, we use the `request` field corresponding to GenerateContentRequest
                    exam_id = getattr(exam, 'id', 'exam')
                    request_entry = {
                        "request": {
                            "contents": [
                                {"parts": [{"text": full_prompt}]}
                            ],
                            # We can also specify generation config here if needed, 
                            # but usually valid at job level too.
                        },
                        "custom_id": f"{exam_id}-{question.id}" # Unique ID to map answering
                    }
                    requests.append(request_entry)
                    
                except Exception as e:
                    step_logger.error(f"[BatchRunner] Failed to build prompt for Q{question.id}: {e}")
        
        # Sort requests by custom_id (optional, but good for consistency)
        requests.sort(key=lambda x: x["custom_id"])

        # Write to JSONL
        with open(output_path, 'w', encoding='utf-8') as f:
            for req in requests:
                f.write(json.dumps(req) + "\n")
                
        step_logger.info(f"[BatchRunner] Wrote {len(requests)} requests to {output_path}")
        return len(requests)

    def _build_prompt_for_question(self, question: Question, use_rag: bool, top_k: int = 5) -> str:
        """Build the full prompt (system + context + question) for a single question."""
        formatted_question = self._format_question_prompt(question)
        
        if not use_rag:
            # Direct prompt
            return f"{self.prompt_builder.build_system_prompt()}\n\n{formatted_question}"
        
        # RAG prompt
        # 1. Collect context
        context_result = self.context_collector.collect(
            query=question.text, # Use clean text for retrieval
            top_k=top_k
        )
        
        # 2. Build context string
        context_str = self.prompt_builder.build_context(context_result.chunks)
        
        # 3. Assemble full prompt
        system_prompt = self.prompt_builder.build_system_prompt()
        
        if context_str:
            full_prompt = f"""{system_prompt}

CONTEXTO LEGAL RELEVANTE:
{context_str}

---

{formatted_question}"""
        else:
            full_prompt = f"{system_prompt}\n\n{formatted_question}"
            
        return full_prompt

    def _format_question_prompt(self, question: Question) -> str:
        """Format a question into a prompt string with options."""
        lines = [question.text, ""]
        for letter in sorted(question.options.keys()):
            lines.append(f"{letter}) {question.options[letter]}")
        return "\n".join(lines)

    def submit_batch(self, file_path: str, display_name: str) -> Any:
        """Upload file and submit batch job."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Batch file not found: {file_path}")
            
        # 1. Upload file
        uploaded_file_name = self.llm_provider.upload_file_for_batch(file_path)
        
        # 2. Create batch job
        job = self.llm_provider.create_batch_job(
            dataset_source=uploaded_file_name,
            display_name=display_name
        )
        return job

    def process_results(self, job_name: str, exam: Exam) -> Dict[str, Any]:
        """
        Retrieve and process results for a completed batch job.
        
        Args:
            job_name: The resource name of the batch job
            exam: The original exam object (to map questions back)
            
        Returns:
            Dict containing aggregated results and scores
        """
        import re
        import requests as http_requests  # Avoid conflict with 'requests' list variable
        
        # 1. Get job status
        job = self.llm_provider.get_batch_job(job_name)
        
        if str(job.state) != "JobState.JOB_STATE_SUCCEEDED":
            step_logger.warning(f"[BatchRunner] Job {job_name} state is {job.state}, not SUCCEEDED.")
            if str(job.state) in ["JobState.JOB_STATE_FAILED", "JobState.JOB_STATE_CANCELLED"]:
                raise RuntimeError(f"Batch job failed: {getattr(job, 'error', 'Unknown error')}")
        
        step_logger.info(f"[BatchRunner] Processing results for job {job_name}")
        
        # 2. Access output from job.dest
        # For file-based input, the SDK returns job.dest.file_name containing results
        dest = getattr(job, 'dest', None)
        step_logger.info(f"[BatchRunner] Job dest: {dest}")
        
        # Try to get file_name from dest (for file-based results)
        output_file_name = getattr(dest, 'file_name', None) if dest else None
        
        # Try to get inlined_responses (for inline-based results)
        inlined_responses = getattr(dest, 'inlined_responses', None) if dest else None
        
        if inlined_responses:
            step_logger.info(f"[BatchRunner] Found {len(inlined_responses)} inlined responses")
            return self._process_inlined_responses(inlined_responses, exam)
        
        if output_file_name:
            step_logger.info(f"[BatchRunner] Output file: {output_file_name}")
            # Try to download file content via Files API
            return self._process_file_output(output_file_name, exam)
        
        # Fallback: check for gcs_uri (Vertex AI path)
        gcs_uri = getattr(dest, 'gcs_uri', None) if dest else None
        if gcs_uri:
            step_logger.warning(f"[BatchRunner] Output is at GCS: {gcs_uri}. GCS download not implemented.")
            return {"status": "GCS_OUTPUT", "gcs_uri": gcs_uri, "info": "Download from GCS manually."}
        
        step_logger.error(f"[BatchRunner] Could not determine output location from job.dest: {dest}")
        return {"status": "UNKNOWN_OUTPUT", "info": "Could not find output in job.dest"}

    def _process_inlined_responses(self, inlined_responses, exam: Exam) -> Dict[str, Any]:
        """Process results from inlined_responses."""
        import re
        
        # Create question map by ID
        question_map = {q.id: q for q in exam.questions}
        
        correct_count = 0
        incorrect_count = 0
        unanswered_count = 0
        
        for resp in inlined_responses:
            # Each response has custom_id and response
            custom_id = getattr(resp, 'custom_id', None)
            response_obj = getattr(resp, 'response', None)
            
            if not custom_id:
                continue
                
            # Parse question ID from custom_id (format: "exam-{question_id}")
            try:
                question_id = int(custom_id.split('-')[-1])
            except (ValueError, IndexError):
                step_logger.warning(f"Could not parse question ID from custom_id: {custom_id}")
                continue
            
            question = question_map.get(question_id)
            if not question:
                continue
            
            # Extract answer from response
            model_answer = None
            if response_obj:
                # Try to get text from response
                try:
                    text = response_obj.candidates[0].content.parts[0].text
                    model_answer = self._extract_answer(text)
                except (AttributeError, IndexError):
                    pass
            
            if model_answer and question.correct_answer:
                if model_answer.lower() == question.correct_answer.lower():
                    correct_count += 1
                else:
                    incorrect_count += 1
            else:
                unanswered_count += 1
        
        total = len(exam.questions)
        gradable = total - unanswered_count
        score = (correct_count / gradable * 100) if gradable > 0 else 0.0
        
        return {
            "score_percent": score,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "unanswered_count": unanswered_count,
            "total_questions": total
        }

    def _process_file_output(self, file_name: str, exam: Exam) -> Dict[str, Any]:
        """Process results from file-based output."""
        import json
        import re
        
        step_logger.info(f"[BatchRunner] Downloading result file: {file_name}")
        
        try:
            # Use the SDK's files.download() method
            file_content = self.llm_provider._client.files.download(file=file_name)
            content_str = file_content.decode('utf-8')
            step_logger.info(f"[BatchRunner] Downloaded {len(content_str)} bytes")
            
            # Parse JSONL content
            # Create question map by ID
            question_map = {q.id: q for q in exam.questions}
            
            correct_count = 0
            incorrect_count = 0
            unanswered_count = 0
            
            for line in content_str.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    result = json.loads(line)
                    custom_id = result.get('custom_id')
                    response = result.get('response', {})
                    
                    if not custom_id:
                        continue
                    
                    # Parse question ID from custom_id (format: "exam-{question_id}")
                    try:
                        question_id = int(custom_id.split('-')[-1])
                    except (ValueError, IndexError):
                        step_logger.warning(f"Could not parse question ID from custom_id: {custom_id}")
                        continue
                    
                    question = question_map.get(question_id)
                    if not question:
                        continue
                    
                    # Extract answer from response
                    model_answer = None
                    try:
                        # Response structure: response.candidates[0].content.parts[0].text
                        candidates = response.get('candidates', [])
                        if candidates:
                            parts = candidates[0].get('content', {}).get('parts', [])
                            if parts:
                                text = parts[0].get('text', '')
                                model_answer = self._extract_answer(text)
                    except (KeyError, IndexError) as e:
                        step_logger.warning(f"Failed to extract answer for {custom_id}: {e}")
                    
                    if model_answer and question.correct_answer:
                        if model_answer.lower() == question.correct_answer.lower():
                            correct_count += 1
                        else:
                            incorrect_count += 1
                    else:
                        unanswered_count += 1
                        
                except json.JSONDecodeError as e:
                    step_logger.warning(f"Failed to parse JSONL line: {e}")
            
            total = len(exam.questions)
            gradable = total - unanswered_count
            score = (correct_count / gradable * 100) if gradable > 0 else 0.0
            
            return {
                "score_percent": score,
                "correct_count": correct_count,
                "incorrect_count": incorrect_count,
                "unanswered_count": unanswered_count,
                "total_questions": total
            }
            
        except Exception as e:
            step_logger.error(f"[BatchRunner] Failed to download/parse file: {e}")
            return {
                "status": "FILE_DOWNLOAD_ERROR",
                "file_name": file_name,
                "error": str(e)
            }

    def _extract_answer(self, text: str) -> Optional[str]:
        """Extract the answer letter from model response."""
        import re
        text = text.strip().lower()
        # Match single letter at start or end
        match = re.match(r'^([a-d])$', text)
        if match:
            return match.group(1)
        # Check if starts with a letter followed by )
        match = re.match(r'^([a-d])\)', text)
        if match:
            return match.group(1)
        # Just take first character if it's a-d
        if len(text) >= 1 and text[0] in 'abcd':
            return text[0]
        return None
