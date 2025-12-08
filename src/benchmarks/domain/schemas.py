"""
Domain schemas for the Benchmarking System.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Question:
    """Represents a single multiple-choice question from an exam."""
    id: int
    text: str
    options: Dict[str, str]  # e.g., {"a": "Option A text", "b": "Option B text"}
    correct_answer: Optional[str] = None  # The correct option letter (a, b, c, d)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "options": self.options,
            "correct_answer": self.correct_answer,
        }


@dataclass
class Exam:
    """Represents a parsed exam containing multiple questions."""
    name: str
    questions: List[Question] = field(default_factory=list)
    source_file: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)  # e.g., date, subject

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "questions": [q.to_dict() for q in self.questions],
            "source_file": self.source_file,
            "metadata": self.metadata,
        }


@dataclass
class QuestionResult:
    """Result of a single question in the benchmark."""
    question_id: int
    model_answer: Optional[str]  # The answer the model gave (a, b, c, d or parsing failure)
    correct_answer: Optional[str]
    is_correct: Optional[bool]  # None if correct_answer is unknown
    raw_response: str  # Full raw response from the model

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "model_answer": self.model_answer,
            "correct_answer": self.correct_answer,
            "is_correct": self.is_correct,
            "raw_response": self.raw_response,
        }


@dataclass
class BenchmarkRun:
    """Represents a single benchmark run configuration."""
    run_id: str
    exam_name: str
    model_name: str
    use_rag: bool = True
    timestamp: datetime = field(default_factory=datetime.now)
    parameters: Dict[str, any] = field(default_factory=dict)  # e.g., top_k, temperature

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "exam_name": self.exam_name,
            "model_name": self.model_name,
            "use_rag": self.use_rag,
            "timestamp": self.timestamp.isoformat(),
            "parameters": self.parameters,
        }


@dataclass
class BenchmarkResult:
    """
    Result of a complete benchmark run.
    """
    run: BenchmarkRun
    results: List[QuestionResult] = field(default_factory=list)
    total_questions: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    unanswered_count: int = 0  # Questions where parsing LLM response failed
    execution_time_ms: float = 0.0

    @property
    def score(self) -> float:
        """Calculate the score as a percentage."""
        if self.total_questions == 0:
            return 0.0
        gradable = self.total_questions - self.unanswered_count
        if gradable == 0:
            return 0.0
        return (self.correct_count / gradable) * 100

    def to_dict(self) -> dict:
        return {
            "run": self.run.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "total_questions": self.total_questions,
            "correct_count": self.correct_count,
            "incorrect_count": self.incorrect_count,
            "unanswered_count": self.unanswered_count,
            "score_percent": self.score,
            "execution_time_ms": self.execution_time_ms,
        }
