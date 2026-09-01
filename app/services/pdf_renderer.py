"""
In-Memory PDF Page Renderer Service
Uses PyMuPDF (fitz) to convert PDF pages directly into PNG byte streams in memory.
Completely stateless and disk-free for enterprise cloud environments.
"""

import io
import logging
from typing import List, Dict, Any
import pymupdf

logger = logging.getLogger(__name__)


class PDFRenderError(Exception):
    """Raised when PDF validation or rendering fails."""
    pass


class PDFRenderer:
    """
    Renders PDF document pages to PNG byte buffers in memory.
    """

    def __init__(self, dpi: int = 200):
        """
        :param dpi: Resolution for rendering pages. 200 DPI gives great OCR quality without excessive memory.
        """
        self.dpi = dpi
        self.zoom = dpi / 72.0  # 72 points per inch standard PDF coordinate system
        self.matrix = pymupdf.Matrix(self.zoom, self.zoom)

    def validate_and_render(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Validates the PDF bytes and renders all pages to PNG byte streams in memory.

        :param pdf_bytes: Raw binary bytes of the uploaded PDF.
        :return: List of dicts containing page_num, total_pages, and png_bytes.
        :raises PDFRenderError: If the input is invalid, corrupted, or password-protected.
        """
        if not pdf_bytes:
            raise PDFRenderError("The uploaded PDF file is empty.")

        # Check for standard PDF file magic header (%PDF-)
        if not pdf_bytes.startswith(b"%PDF-"):
            raise PDFRenderError("Invalid file format: File header does not match PDF specification (%PDF-).")

        try:
            # Open PDF from in-memory byte buffer
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.error("Failed to parse PDF stream: %s", e)
            raise PDFRenderError(f"Corrupted or unreadable PDF document: {e}")

        try:
            if doc.is_encrypted:
                raise PDFRenderError("The uploaded PDF is password-protected or encrypted. Please provide an unencrypted PDF.")

            total_pages = len(doc)
            if total_pages == 0:
                raise PDFRenderError("The PDF document contains 0 pages.")

            logger.info("Rendering %d pages at %d DPI in-memory...", total_pages, self.dpi)
            rendered_pages = []

            for page_idx in range(total_pages):
                page_num = page_idx + 1
                page = doc.load_page(page_idx)
                
                # Render page to RGB pixmap without alpha channel
                pix = page.get_pixmap(matrix=self.matrix, alpha=False)
                
                # Output directly to PNG bytes in memory
                png_bytes = pix.tobytes("png")

                rendered_pages.append({
                    "page_num": page_num,
                    "total_pages": total_pages,
                    "width": pix.width,
                    "height": pix.height,
                    "png_bytes": png_bytes
                })

            return rendered_pages

        finally:
            doc.close()
