"""
Parser service for converting exam text files to structured Exam objects.
Uses robust regex patterns assuming a consistent input format.
"""
import re
from typing import List, Optional, Tuple, Dict
from pathlib import Path

from src.benchmarks.domain.schemas import Question, Exam


class ExamParserService:
    """
    Parses raw text exam files into Exam domain objects.
    
    Expected format:
    - Questions start with "NUMBER.- " or "NUMBER. -" (e.g., "1.- ", "23. - ")
    - Options start with "LETTER)" (e.g., "a)", "b)", etc.)
    - Multi-line questions and options are supported.
    - Answer key at the end: "NUMBER LETTER" pattern (e.g., "1 B", "2 A")
    """

    # Regex for question start: captures the question number
    # Supports hyphen, en-dash, em-dash
    QUESTION_PATTERN = re.compile(
        r"^(\d+)[\.\s]*[–—-]\s*(.+)",
        re.MULTILINE
    )
    
    # Regex for option start: captures the letter and option text
    OPTION_PATTERN = re.compile(
        r"^([a-dA-D])\)\s*(.+)",
        re.MULTILINE
    )
    
    # Regex for answer key entries: "NUMBER LETTER" or "NUMBER. LETTER"
    ANSWER_KEY_PATTERN = re.compile(
        r"^(\d+)[\.\s]+([A-Da-d])\s*$",
        re.MULTILINE
    )
    
    # PDF artifact patterns to remove (headers, footers, page numbers)
    PDF_ARTIFACT_PATTERNS = [
        # BOE header pattern (captures various date formats and contexts)
        re.compile(
            r"Acuerdo de \d+ de \w+ de \d{4} de la Comisión de Selección[^\.]*\.[^\n]*",
            re.IGNORECASE
        ),
        # Acuerdo header in answer key section (more flexible pattern)
        re.compile(
            r"Acuerdo de \d+ de \w+ de \d{4} del Tribunal calificador[^\n]*(?:\n[^\n]*)*?(?=\d+\s*[A-D]|\Z)",
            re.IGNORECASE
        ),
        # Exercise header pattern
        re.compile(
            r"PRIMER EJERCICIO\s*[–—-]\s*\d+\s+DE\s+\w+\s+DE\s+\d{4}",
            re.IGNORECASE
        ),
        # Page number pattern
        re.compile(
            r"P[áa]gina\s+\d+",
            re.IGNORECASE
        ),
        # Answer key header institutional names (multi-line headers from PDF)
        # Use flexible whitespace (\s+) between words
        re.compile(
            r"CONSEJO\s+GENERAL\s+DEL\s+(?:PODER\s+JUDICIAL)?",
            re.IGNORECASE
        ),
        re.compile(
            r"FISCALÍA\s+GENERAL\s+(?:DEL\s+ESTADO)?",
            re.IGNORECASE
        ),
        re.compile(
            r"MINISTERIO\s+DE\s+LA\s+PRESIDENCIA[^\.]*?CORTES",
            re.IGNORECASE | re.DOTALL
        ),
        re.compile(
            r"Comisi[oó]n\s+de\s+Selecci[oó]n",
            re.IGNORECASE
        ),
    ]

    def _clean_pdf_artifacts(self, text: str) -> str:
        """
        Remove PDF artifacts (headers, footers, page numbers) from text.
        
        Args:
            text: Raw text that may contain PDF artifacts
            
        Returns:
            Cleaned text with artifacts removed
        """
        for pattern in self.PDF_ARTIFACT_PATTERNS:
            text = pattern.sub("", text)
        
        # Clean up any resulting double spaces or multiple newlines
        text = re.sub(r"  +", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        
        return text.strip()

    def parse_text(self, text: str, exam_name: str = "Unnamed Exam", source_file: Optional[str] = None) -> Exam:
        """
        Parse the given raw text and return an Exam object.
        
        Args:
            text: Raw text content of the exam.
            exam_name: Name for the exam.
            source_file: Optional path to the source file.
            
        Returns:
            An Exam object with parsed questions and answers.
        """
        # First, extract answer keys from the end of the file
        answer_keys = self._extract_answer_keys(text)
        
        # Then extract questions
        questions = self._extract_questions(text)
        
        # Apply answer keys to questions
        for q in questions:
            if q.id in answer_keys:
                q.correct_answer = answer_keys[q.id].lower()
        
        return Exam(
            name=exam_name,
            questions=questions,
            source_file=source_file,
        )

    def parse_file(self, file_path: str, exam_name: Optional[str] = None) -> Exam:
        """
        Parse an exam from a file path.
        
        Args:
            file_path: Path to the text file.
            exam_name: Optional name for the exam (defaults to file name).
            
        Returns:
            An Exam object.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Exam file not found: {file_path}")
        
        text = path.read_text(encoding="utf-8")
        name = exam_name or path.stem
        
        return self.parse_text(text, exam_name=name, source_file=str(path))

    def _extract_answer_keys(self, text: str) -> Dict[int, str]:
        """
        Extract answer keys from the text.
        
        Looks for patterns like:
        - "1 B"
        - "1. B"
        - "10 A"
        
        Returns:
            Dict mapping question ID to answer letter.
        """
        answers: Dict[int, str] = {}
        
        matches = self.ANSWER_KEY_PATTERN.findall(text)
        for q_num, letter in matches:
            answers[int(q_num)] = letter.upper()
        
        return answers

    def _extract_questions(self, text: str) -> List[Question]:
        """
        Extract all questions from the text.
        
        This method identifies question blocks and then parses options within each block.
        """
        questions: List[Question] = []
        
        # Split text into question blocks
        # Find all question starts
        question_starts = list(self.QUESTION_PATTERN.finditer(text))
        
        if not question_starts:
            return questions
        
        for i, match in enumerate(question_starts):
            q_number = int(match.group(1))
            
            # Determine the end of this question block (start of next question or EOF)
            start_pos = match.start()
            if i + 1 < len(question_starts):
                end_pos = question_starts[i + 1].start()
            else:
                end_pos = len(text)
            
            question_block = text[start_pos:end_pos]
            
            # Parse the question text and options from this block
            q_text, options = self._parse_question_block(question_block, match.group(2))
            
            if q_text:  # Only add if we have valid question text
                questions.append(Question(
                    id=q_number,
                    text=self._clean_pdf_artifacts(q_text.strip()),
                    options={k: self._clean_pdf_artifacts(v) for k, v in options.items()},
                ))
        
        return questions

    def _parse_question_block(self, block: str, initial_text: str) -> Tuple[str, dict]:
        """
        Parse a single question block to extract the full question text and its options.
        
        Args:
            block: The full text block for one question.
            initial_text: The initial text captured after the question number.
            
        Returns:
            Tuple of (full_question_text, options_dict)
        """
        options: dict = {}
        
        # Find all option matches
        option_matches = list(self.OPTION_PATTERN.finditer(block))
        
        if not option_matches:
            # No options found, entire block (minus the number prefix) is the question
            # Remove the "N.- " or "N. - " prefix
            clean_block = re.sub(r"^\d+[\.\s]*-\s*", "", block, count=1).strip()
            return clean_block, options
        
        # Question text is from the start of initial_text to the first option
        first_option_pos = option_matches[0].start()
        
        # The question text is everything from the initial text capture up to the first option
        # We need to find where in the block the initial_text ends vs. where options begin
        # The block starts with "N.- initial_text..." so we find first option in block
        question_text_end = first_option_pos
        
        # Get the question text (block from start to first option, minus the "N.-" prefix)
        question_full = re.sub(r"^\d+[\.\s]*-\s*", "", block[:question_text_end], count=1).strip()
        
        # Parse each option
        for j, opt_match in enumerate(option_matches):
            letter = opt_match.group(1).lower()
            
            # Option text goes from this match to the next option or end of block
            opt_start = opt_match.end()
            if j + 1 < len(option_matches):
                opt_end = option_matches[j + 1].start()
            else:
                opt_end = len(block)
            
            # Get the option text, including any continuation lines
            # The captured group(2) is just the first line, we need to extend to opt_end
            option_text = opt_match.group(2)
            remaining = block[opt_match.end():opt_end].strip()
            if remaining:
                option_text = option_text + " " + remaining
            
            # Clean up whitespace
            option_text = " ".join(option_text.split())
            options[letter] = option_text
        
        return question_full, options
