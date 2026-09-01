"""
Conversion Pipeline Orchestrator
Coordinates in-memory PDF rendering, asynchronous VLM OCR extraction, and DOCX document synthesis.
"""

import asyncio
import io
import time
import logging
from typing import Dict, Any, Tuple

from app.services.pdf_renderer import PDFRenderer, PDFRenderError
from app.services.vlm_ocr import VLMExtractor, VLMExtractionError
from app.services.docx_builder import DocxBuilder
from app.config import settings

logger = logging.getLogger(__name__)


class ConversionPipeline:
    """
    Orchestrates the end-to-end PDF to Word conversion pipeline.
    """

    def __init__(self):
        self.renderer = PDFRenderer(dpi=settings.render_dpi)
        self.extractor = VLMExtractor()
        self.builder = DocxBuilder()

    async def convert_pdf_to_word(
        self,
        pdf_bytes: bytes,
        filename: str = "document.pdf"
    ) -> Tuple[io.BytesIO, Dict[str, Any]]:
        """
        Executes the full in-memory PDF to DOCX conversion pipeline.

        :param pdf_bytes: Raw binary bytes of the PDF.
        :param filename: Original filename from request headers.
        :return: Tuple of (docx_bytes_io, execution_metadata_dict)
        """
        total_start = time.time()
        logger.info("Starting conversion pipeline for '%s' (%d bytes)...", filename, len(pdf_bytes))

        # 1. In-memory page rendering to PNG byte streams (offloaded to thread to avoid blocking event loop)
        render_start = time.time()
        rendered_pages = await asyncio.to_thread(self.renderer.validate_and_render, pdf_bytes)
        render_elapsed = round(time.time() - render_start, 3)
        total_pages = len(rendered_pages)
        logger.info("Rendered %d pages in %.2fs", total_pages, render_elapsed)

        # 2. Async concurrent Qwen3.7-Flash VLM OCR extraction
        ocr_start = time.time()
        ocr_pages = await self.extractor.extract_document(rendered_pages)
        ocr_elapsed = round(time.time() - ocr_start, 3)
        
        total_prompt_tokens = sum(p.get("prompt_tokens", 0) for p in ocr_pages)
        total_completion_tokens = sum(p.get("completion_tokens", 0) for p in ocr_pages)
        total_tokens = sum(p.get("total_tokens", 0) for p in ocr_pages)
        
        logger.info("Extracted %d pages via %s in %.2fs (Total tokens: %d)",
                    total_pages, settings.model_name, ocr_elapsed, total_tokens)

        # 3. Native DOCX synthesis (offloaded to thread to avoid blocking event loop)
        docx_start = time.time()
        docx_stream = await asyncio.to_thread(self.builder.build_docx, ocr_pages, doc_title=filename)
        docx_elapsed = round(time.time() - docx_start, 3)
        
        total_elapsed = round(time.time() - total_start, 3)
        logger.info("Generated DOCX for '%s' in %.2fs (Total pipeline time: %.2fs)",
                    filename, docx_elapsed, total_elapsed)

        meta = {
            "filename": filename,
            "total_pages": total_pages,
            "total_tokens": total_tokens,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "render_time_sec": render_elapsed,
            "ocr_time_sec": ocr_elapsed,
            "docx_time_sec": docx_elapsed,
            "total_time_sec": total_elapsed
        }

        return docx_stream, meta
