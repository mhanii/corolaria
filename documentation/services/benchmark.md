# Benchmark Service

## Overview

The **Benchmark Service** provides a framework for evaluating the performance of the Coloraria RAG pipeline and LLM models against legal exams. It supports running multiple-choice questions (exams) and scoring the results based on correct/incorrect answers.

**Location**: `src/benchmarks/`

## Components

### 1. Benchmark Runner (`BenchmarkRunner`)
*   **Source**: `src/benchmarks/services/runner.py`
*   **Role**: Orchestrates the execution of exams.
*   **Modes**:
    *   **Direct LLM**: Sends questions directly to the LLM (no context), useful for establishing a baseline (Zero-shot).
    *   **RAG**: Uses the `ChatService` to retrieve context for each question before answering.

### 2. Domain Models
*   **Source**: `src/benchmarks/domain/schemas.py`
*   **`Exam`**: Collection of `Question`s.
*   **`Question`**: A multiple-choice question with text, options (a, b, c, d), and the correct answer.
*   **`BenchmarkResult`**: Aggregated results including score percentage, execution time, and individual question details.

## Logic Flow

1.  **Initialization**: Runner is initialized with an `LLMProvider` and optional `ChatService`.
2.  **Exam Execution**:
    *   Iterates through each question in the exam.
    *   **Retry Mechanism**: Implements exponential backoff (1s, 2s, 4s) for transient network errors (timeouts, connection errors).
    *   **Prompting**: Formats question and options. Adds system prompt instructing the model to output *only* the letter (a, b, c, d).
    *   **Extraction**: Heuristically extracts the answer letter from the model's response (handles "Option A", "a)", "(a)", etc.).
3.  **Scoring**: Compares extracted answer with `correct_answer`. Calculates final percentage.

## Usage

```python
from src.benchmarks.services.runner import BenchmarkRunner
from src.benchmarks.domain.schemas import Exam, Question

# Initialize
runner = BenchmarkRunner(llm_provider=my_provider, chat_service=my_chat_service)

# Run Exam
result = runner.run_exam(
    exam=my_exam,
    model_name="gemini-pro",
    parameters={"top_k": 5}
)

# Output results
print(f"Score: {result.score}%")
```

## Special Features

*   **Robust Answer Extraction**: various regex patterns to catch correct answers even if the LLM is chatty.
*   **Error Handling**: Continues exam even if individual questions fail (after retries), marking them as errors.
*   **Observability**: Logs detailed results per question.
