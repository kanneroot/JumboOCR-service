"""
API Route Definitions for PDF to Word Conversion Microservice.
Provides raw binary streaming endpoints and health check probes.
"""

import io
import re
import urllib.parse
import logging
from typing import Optional

from fastapi import APIRouter, Request, Header, HTTPException, status
from fastapi.responses import Response, JSONResponse

from app.config import settings
from app.services.pdf_renderer import PDFRenderError
from app.services.vlm_ocr import VLMExtractionError

logger = logging.getLogger(__name__)

router = APIRouter()


def extract_filename_from_header(content_disposition: Optional[str]) -> str:
    """
    Extracts filename from Content-Disposition header using Python standard library re/urllib.
    Examples:
      - filename="invoice.pdf"
      - filename=document.pdf
      - filename*=UTF-8''my%20invoice.pdf
    """
    if not content_disposition:
        return "document.pdf"

    # Match RFC 5987 filename*=UTF-8''...
    rfc5987_match = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')([^\s;]+)", content_disposition)
    if rfc5987_match:
        return urllib.parse.unquote(rfc5987_match.group(1))

    # Match standard filename="..." or filename=...
    standard_match = re.search(r'filename\s*=\s*"?([^";\n]+)"?', content_disposition)
    if standard_match:
        return standard_match.group(1).strip()

    return "document.pdf"


@router.get("/health", tags=["Monitoring"])
@router.get("/api/v1/health", tags=["Monitoring"])
async def health_check():
    """
    Health check probe returning service status, model configuration, and runtime info.
    Note: For public-facing deployments, consider restricting the response to
    {"status": "healthy"} and moving detailed info behind an authenticated endpoint.
    """
    return {
        "status": "healthy",
        "service": "pdf-to-word-microservice",
        "model": settings.model_name,
        "render_dpi": settings.render_dpi,
        "max_concurrent_pages": settings.max_concurrent_pages,
        "api_key_configured": bool(settings.dashscope_api_key)
    }


@router.post(
    "/api/v1/convert",
    summary="Convert PDF Binary to Word DOCX Binary",
    description="""
    Receives a raw PDF binary stream in the HTTP request body and returns a Microsoft Word (.docx) binary stream.

    **Headers required:**
    - `Content-Type: application/pdf` (or `application/octet-stream`)
    - `Content-Disposition: filename="input.pdf"` (Optional, extracts original filename)

    **Response:**
    - `Content-Type: application/octet-stream`
    - `Content-Disposition: filename="output.docx"`
    - Body: Raw DOCX binary payload
    """,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "Successful conversion returning Word .docx binary payload"
        },
        400: {"description": "Invalid input format or corrupt PDF"},
        413: {"description": "Payload too large"},
        500: {"description": "Internal server or VLM extraction failure"}
    },
    tags=["Conversion"]
)
async def convert_pdf_binary(
    request: Request,
    content_type: Optional[str] = Header(None, alias="Content-Type"),
    content_disposition: Optional[str] = Header(None, alias="Content-Disposition")
):
    """
    Primary Raw Binary PDF-to-Word Conversion Endpoint.
    """
    # 1. Validate Content-Type header if provided
    if content_type and not (
        "application/pdf" in content_type.lower() or
        "application/octet-stream" in content_type.lower()
    ):
        logger.warning("Rejected request with invalid Content-Type: %s", content_type)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Content-Type '{content_type}'. Expected 'application/pdf' or 'application/octet-stream'."
        )

    # 2. Extract original filename
    orig_filename = extract_filename_from_header(content_disposition)
    doc_stem = re.sub(r'\.pdf$', '', orig_filename, flags=re.IGNORECASE) or "output"
    out_filename = f"{doc_stem}.docx"

    # 3. Early rejection via Content-Length header (before reading body into memory)
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    content_length_str = request.headers.get("content-length")
    if content_length_str:
        try:
            if int(content_length_str) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Content-Length ({int(content_length_str) / (1024*1024):.1f} MB) exceeds maximum allowed size ({settings.max_file_size_mb} MB)."
                )
        except ValueError:
            pass

    # 4. Read raw PDF binary stream from body
    pdf_bytes = await request.body()
    file_size_bytes = len(pdf_bytes)

    if file_size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty request body. Please send the raw PDF binary in the HTTP body."
        )

    # Validate actual file size (defense in depth for chunked transfers without Content-Length)
    if file_size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({file_size_bytes / (1024*1024):.1f} MB) exceeds maximum allowed size ({settings.max_file_size_mb} MB)."
        )

    # 5. Execute conversion pipeline
    try:
        pipeline = request.app.state.pipeline
        docx_stream, meta = await pipeline.convert_pdf_to_word(pdf_bytes, filename=orig_filename)
    except PDFRenderError as e:
        logger.warning("PDF Render error for %s: %s", orig_filename, e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except VLMExtractionError as e:
        logger.error("VLM Extraction error for %s: %s", orig_filename, e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error during PDF to Word conversion: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal conversion error: {str(e)}"
        )

    docx_bytes = docx_stream.getvalue()

    # 5. Return raw DOCX binary with requested headers
    # Supports both Content-Disposition: filename="output.docx" and attachment; filename="output.docx"
    return Response(
        content=docx_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'filename="{out_filename}"',
            "X-Converted-Pages": str(meta["total_pages"]),
            "X-Process-Time-Sec": str(meta["total_time_sec"]),
            "X-Total-Tokens": str(meta["total_tokens"])
        }
    )
