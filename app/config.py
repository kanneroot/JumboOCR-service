"""
Configuration module for PDF to Word Microservice.
Built strictly with Python Standard Library (no pydantic-settings or python-dotenv).
"""

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


def load_dotenv(dotenv_path: Optional[Path] = None) -> None:
    """
    Lightweight .env file parser using Python standard library.
    Loads KEY=VALUE pairs into os.environ if not already set.
    """
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    
    if not dotenv_path.exists():
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    # Set in os.environ if not already set
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception as e:
        logging.warning("Failed to read .env file at %s: %s", dotenv_path, e)


# Load environment variables on module import
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """
    Application runtime configuration settings.
    """
    # Alibaba Cloud DashScope credentials
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_base_url: str = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://ws-11apde4s0qdodprl.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    )
    
    # Model specification
    model_name: str = os.getenv("MODEL_NAME", "qwen3.7-flash")
    
    # PDF Rendering resolution
    render_dpi: int = int(os.getenv("RENDER_DPI", "200"))
    
    # Concurrency control for multi-page documents
    max_concurrent_pages: int = int(os.getenv("MAX_CONCURRENT_PAGES", "6"))
    
    # File upload limits (MB)
    max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    
    # Server network settings
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Standard OCR Prompt for Qwen Vision-Language Model
    ocr_prompt: str = (
        "你是一個精確的文件 OCR 與排版引擎。\n"
        "請將圖片中的所有文字、表格、編號、數字、金額與標題，忠實且精確地轉錄為清晰的 Markdown 格式。\n"
        "要求：\n"
        "1. 保持繁體中文原始字形，不要任意簡繁轉換。\n"
        "2. 表格請使用標準 Markdown 表格語法（| col1 | col2 |）對齊排列。\n"
        "3. 嚴禁任何開場白、問候語、前言（如「以下是辨識結果...」）或結語。只輸出轉錄後的 Markdown 本體內容。"
    )


@lru_cache()
def get_settings() -> Settings:
    """Factory function for Settings. Call get_settings.cache_clear() in tests to reset."""
    return Settings()


# Singleton instance (backward compatible import)
settings = get_settings()
