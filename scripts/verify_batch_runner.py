
import sys
import os
import json
from unittest.mock import MagicMock
from src.benchmarks.domain.schemas import Exam, Question
from src.benchmarks.services.batch_runner import BatchBenchmarkRunner

# Mock dependencies
mock_llm = MagicMock()
mock_llm.upload_file_for_batch.return_value = "files/12345"
mock_llm.create_batch_job.return_value = MagicMock(name="job/123", state="JOB_STATE_ACTIVE")

mock_context = MagicMock()
# Return dummy chunks
mock_context.collect.return_value = MagicMock(chunks=[{"article_text": "Sample context", "score": 0.9}])

# Create dummy exam
questions = [
    Question(id=1, text="What is X?", options={"a": "X1", "b": "X2"}, correct_answer="a"),
    Question(id=2, text="What is Y?", options={"a": "Y1", "b": "Y2"}, correct_answer="b"),
]
exam = Exam(name="Test Exam", questions=questions)

# Initialize runner
runner = BatchBenchmarkRunner(llm_provider=mock_llm, context_collector=mock_context)

# 1. Test prepare_batch_file
output_file = "test_batch.jsonl"
print(f"Preparing batch file: {output_file}")
count = runner.prepare_batch_file(exam, output_file, use_rag=True)

print(f"Requests written: {count}")
assert count == 2

# Verify file content
print("Verifying content:")
with open(output_file, 'r') as f:
    lines = f.readlines()
    for line in lines:
        data = json.loads(line)
        print(f"  - custom_id: {data.get('custom_id')}")
        # Check prompt contains context
        text = data["request"]["contents"][0]["parts"][0]["text"]
        assert "CONTEXTO LEGAL" in text
        assert "Sample context" in text

# 2. Test submit_batch
print("Submitting batch...")
job = runner.submit_batch(output_file, display_name="Test Batch")
print(f"Job submitted: {job.name}")

# Verify mocks called
mock_llm.upload_file_for_batch.assert_called_with(output_file)
mock_llm.create_batch_job.assert_called()

# Cleanup
if os.path.exists(output_file):
    os.remove(output_file)

print("Verification SUCCESS!")
