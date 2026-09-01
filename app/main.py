"""
FastAPI Microservice Entrypoint for PDF to Word Conversion Service.
Provides high-performance async API with enterprise standard error handling.
"""

import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import router
from app.services.pipeline import ConversionPipeline

# Configure standard library logging
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("pdf_to_word_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Microservice lifecycle event hooks (startup / shutdown)."""
    logger.info("=======================================================")
    logger.info(" Starting PDF to Word Enterprise Microservice")
    logger.info(" Model: %s | DPI: %d | Workers: %d",
                settings.model_name, settings.render_dpi, settings.max_concurrent_pages)
    logger.info(" DashScope API Key Configured: %s", "YES" if settings.dashscope_api_key else "NO")
    logger.info("=======================================================")
    # Initialize conversion pipeline within the running event loop context
    app.state.pipeline = ConversionPipeline()
    yield
    logger.info("Shutting down PDF to Word Microservice...")


app = FastAPI(
    title="PDF to Word Enterprise Microservice",
    description="High-performance asynchronous microservice converting PDF binary streams to Microsoft Word (.docx) documents using Qwen3.7-Flash VLM.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for cross-origin enterprise clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include conversion and healthcheck routes
app.include_router(router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception fallback returning standardized JSON error schema.
    """
    logger.exception("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred during processing.",
            "detail": str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
