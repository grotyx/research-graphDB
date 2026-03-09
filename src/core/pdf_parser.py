"""PDF Parser module for extracting text and metadata from PDF files."""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF


@dataclass
class PageContent:
    """Content of a single PDF page."""
    page_number: int
    text: str


@dataclass
class DocumentMetadata:
    """Metadata extracted from a document."""
    title: Optional[str]
    author: Optional[str]
    subject: Optional[str]
    creation_date: Optional[datetime]
    page_count: int
    file_path: str
    file_size: int
    source_type: str = "pdf"


@dataclass
class ParseResult:
    """Result of parsing a PDF file."""
    text: str
    pages: list[PageContent]
    metadata: DocumentMetadata


class PDFParseError(Exception):
    """Exception raised when PDF parsing fails."""
    pass


class PDFParser:
    """Parse PDF files to extract text and metadata."""

    def __init__(self, config: dict | None = None):
        """
        Initialize the PDF parser.

        Args:
            config: Optional configuration dictionary
                - extract_images: bool (extract image captions)
                - preserve_layout: bool (preserve text layout)
        """
        self.config = config or {}
        self.preserve_layout = self.config.get("preserve_layout", False)

    def parse(self, file_path: str) -> ParseResult:
        """
        Parse a PDF file and extract text and metadata.

        Args:
            file_path: Path to the PDF file

        Returns:
            ParseResult containing text, pages, and metadata

        Raises:
            FileNotFoundError: If the file doesn't exist
            PDFParseError: If parsing fails
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.suffix.lower() == ".pdf":
            raise PDFParseError(f"Not a PDF file: {file_path}")

        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise PDFParseError(f"Failed to open PDF: {e}")

        try:
            # Extract pages
            pages = []
            all_text_parts = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = self._extract_text_from_page(page)
                pages.append(PageContent(
                    page_number=page_num + 1,
                    text=text
                ))
                all_text_parts.append(text)

            # Extract metadata
            metadata = self._extract_metadata(doc, file_path)

            # Combine all text
            full_text = "\n\n".join(all_text_parts)

            return ParseResult(
                text=full_text,
                pages=pages,
                metadata=metadata
            )

        finally:
            doc.close()

    def extract_metadata(self, file_path: str) -> DocumentMetadata:
        """
        Extract only metadata from a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            DocumentMetadata object
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        doc = None
        try:
            doc = fitz.open(file_path)
            metadata = self._extract_metadata(doc, file_path)
            return metadata
        except Exception as e:
            raise PDFParseError(f"Failed to extract metadata: {e}")
        finally:
            if doc is not None:
                doc.close()

    def _extract_text_from_page(self, page: fitz.Page) -> str:
        """
        Extract text from a single page.

        Args:
            page: PyMuPDF page object

        Returns:
            Extracted text string
        """
        if self.preserve_layout:
            # Use blocks for layout preservation
            blocks = page.get_text("blocks")
            # Sort by y-coordinate then x-coordinate (reading order)
            blocks.sort(key=lambda b: (b[1], b[0]))

            text_parts = []
            for block in blocks:
                if block[6] == 0:  # Text block (not image)
                    text_parts.append(block[4].strip())

            text = "\n".join(text_parts)
        else:
            # Simple text extraction
            text = page.get_text()

        # Clean up the text
        text = self._clean_text(text)

        return text

    def _extract_metadata(self, doc: fitz.Document, file_path: str) -> DocumentMetadata:
        """
        Extract metadata from the PDF document.

        Args:
            doc: PyMuPDF document object
            file_path: Path to the PDF file

        Returns:
            DocumentMetadata object
        """
        meta = doc.metadata

        # Parse creation date
        creation_date = None
        if meta.get("creationDate"):
            creation_date = self._parse_pdf_date(meta["creationDate"])

        # Try to get title from metadata or infer from first page
        title = meta.get("title")
        if not title or title.strip() == "":
            title = self._infer_title(doc)

        return DocumentMetadata(
            title=title,
            author=meta.get("author"),
            subject=meta.get("subject"),
            creation_date=creation_date,
            page_count=len(doc),
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            source_type="pdf"
        )

    def _infer_title(self, doc: fitz.Document) -> str | None:
        """
        Try to infer the title from the first page.

        Args:
            doc: PyMuPDF document object

        Returns:
            Inferred title or None
        """
        if len(doc) == 0:
            return None

        first_page = doc[0]
        blocks = first_page.get_text("blocks")

        if not blocks:
            return None

        # Sort by y-coordinate and get the first text block
        text_blocks = [b for b in blocks if b[6] == 0]
        if not text_blocks:
            return None

        text_blocks.sort(key=lambda b: b[1])

        # Get the first non-empty text as potential title
        for block in text_blocks[:3]:  # Check first 3 blocks
            text = block[4].strip()
            if text and len(text) > 5 and len(text) < 300:
                # Clean up and return first line
                lines = text.split("\n")
                title = lines[0].strip()
                if len(title) > 5:
                    return title

        return None

    def _parse_pdf_date(self, date_str: str) -> datetime | None:
        """
        Parse PDF date format (D:YYYYMMDDHHmmSS).

        Args:
            date_str: PDF date string

        Returns:
            datetime object or None
        """
        try:
            # Remove 'D:' prefix if present
            if date_str.startswith("D:"):
                date_str = date_str[2:]

            # Parse the date (at least YYYYMMDD)
            if len(date_str) >= 8:
                year = int(date_str[0:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])

                hour = int(date_str[8:10]) if len(date_str) >= 10 else 0
                minute = int(date_str[10:12]) if len(date_str) >= 12 else 0
                second = int(date_str[12:14]) if len(date_str) >= 14 else 0

                return datetime(year, month, day, hour, minute, second)
        except (ValueError, IndexError):
            pass

        return None

    def _clean_text(self, text: str) -> str:
        """
        Clean up extracted text.

        Args:
            text: Raw extracted text

        Returns:
            Cleaned text
        """
        # Replace multiple spaces with single space
        import re
        text = re.sub(r"[ \t]+", " ", text)

        # Replace multiple newlines with double newline
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Strip whitespace from each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        # Remove leading/trailing whitespace
        text = text.strip()

        return text
