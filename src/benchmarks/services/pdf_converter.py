"""
PDF to Text Converter Service.
Converts PDF exam files to plain text for processing.
Uses PyMuPDF (fitz) for fast, accurate extraction.
"""
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


class PDFConverterService:
    """
    Converts PDF files to text.
    
    Usage:
        converter = PDFConverterService()
        text = converter.convert_pdf("exam.pdf")
        # or save to file:
        converter.convert_pdf("exam.pdf", output_path="exam.txt")
    """

    def __init__(self):
        if not HAS_PYMUPDF:
            raise ImportError(
                "PyMuPDF is required for PDF conversion. "
                "Install it with: pip install pymupdf"
            )

    def convert_pdf(
        self,
        pdf_path: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Convert a PDF file to plain text.
        
        Args:
            pdf_path: Path to the PDF file.
            output_path: Optional path to save the text output.
            
        Returns:
            Extracted text content.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"File is not a PDF: {pdf_path}")
        
        # Open and extract text from PDF
        text_parts = []
        with fitz.open(pdf_path) as doc:
            for page_num, page in enumerate(doc):
                page_text = page.get_text("text")
                text_parts.append(page_text)
        
        full_text = "\n".join(text_parts)
        
        # Save to file if output path provided
        if output_path:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(full_text, encoding="utf-8")
        
        return full_text

    def convert_pdf_to_file(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Convert PDF and save to a .txt file with the same name.
        
        Args:
            pdf_path: Path to the PDF file.
            output_dir: Optional output directory (defaults to same dir as PDF).
            
        Returns:
            Path to the output text file.
        """
        pdf = Path(pdf_path)
        
        if output_dir:
            output = Path(output_dir) / f"{pdf.stem}.txt"
        else:
            output = pdf.with_suffix(".txt")
        
        self.convert_pdf(pdf_path, str(output))
        return str(output)
