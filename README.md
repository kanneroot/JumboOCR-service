# PDF to Word Conversion Microservice (`pdf_to_word_service`)

Stateless FastAPI microservice that transforms PDF documents into formatted Microsoft Word (`.docx`) documents using Alibaba Cloud's **Qwen3.7-Flash** Vision-Language Model.

---

## Architecture Overview

```
                      [ Client Application ]
                                │
          POST /api/v1/convert
          Content-Type: application/pdf
          Content-Disposition: filename="input.pdf"
          Body: [Raw PDF Binary Stream]
                                ▼
         ┌────────────────────────────────────────────────────────┐
         │         FastAPI Microservice (pdf_to_word_service)     │
         │                                                        │
         │  1. Request Validation (app/routes.py)                 │
         │     - Validates Content-Type and file size limits      │
         │     - Extracts custom filename via regex               │
         │                                                        │
         │  2. In-Memory PDF Renderer (app/services/pdf_renderer) │
         │     - Validates PDF %PDF- magic signature              │
         │     - PyMuPDF converts pages to PNG in memory (io)     │
         │                                                        │
         │  3. Async Qwen3.7-Flash VLM (app/services/vlm_ocr)     │
         │     - AsyncOpenAI client with asyncio semaphore bounds │
         │     - Exponential backoff retry on rate limits         │
         │     - Structured Markdown OCR transcription            │
         │                                                        │
         │  4. Native DOCX Synthesizer (app/services/docx_builder)│
         │     - AST Markdown parser (Headings, Bold, Lists)      │
         │     - Table parser: creates Word tables with borders,  │
         │       header styling, cell padding & zebra shading     │
         │     - Page breaks between document pages               │
         │     - Writes directly into in-memory io.BytesIO        │
         │                                                        │
         │  5. Response Stream                                    │
         │     - Content-Type: application/octet-stream           │
         │     - Content-Disposition: filename="output.docx"      │
         └────────────────────────────────────────────────────────┘
                                │
                                ▼
                [ HTTP 200: DOCX Binary Stream ]
```

---

## Key Features & Production Standards

- **Dependencies**: Only **4** production packages (`fastapi`, `openai`, `pymupdf`, `python-docx`).

---

## Directory Structure

```
pdf_to_word_service/
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app entrypoint, CORS, exception handlers
│   ├── config.py                 # Pure stdlib configuration (os, pathlib, dataclasses)
│   ├── routes.py                 # POST /api/v1/convert, GET /health
│   └── services/
│       ├── __init__.py
│       ├── pdf_renderer.py       # PyMuPDF in-memory rendering to PNG bytes
│       ├── vlm_ocr.py            # AsyncOpenAI Qwen3.7-Flash VLM client with retries
│       ├── docx_builder.py       # Pure Python Markdown-to-DOCX AST & Table formatter
│       └── pipeline.py           # Orchestrates PDF -> OCR -> DOCX workflow
├── tests/
│   ├── __init__.py
│   └── test_service.py           # Automated unit and integration test suite
├── .env.example                  # Environment configuration template
├── .env                          # Local environment settings (git-ignored in production)
├── Dockerfile                    # Lightweight Python 3.12 slim Docker image
├── docker-compose.yml            # Container orchestration manifest
├── requirements.txt              # Production dependencies
├── requirements-dev.txt          # Development/test dependencies
├── test_convert_pdf.py           # Standalone E2E test client (HTTP + direct pipeline)
└── README.md                     # Microservice documentation
```

---

## API Specification

### 1. Convert PDF to Word (`POST /api/v1/convert`)

#### Request
- **Method**: `POST`
- **Path**: `/api/v1/convert`
- **HTTP Headers**:
  - `Content-Type: application/pdf` (or `application/octet-stream`)
  - `Content-Disposition: filename="input.pdf"` (Optional, provides original document name)
- **HTTP Body**:
  - Raw binary stream of the PDF file.

#### Response
- **Status Code**: `200 OK`
- **HTTP Headers**:
  - `Content-Type: application/octet-stream`
  - `Content-Disposition: filename="output.docx"`
  - `X-Converted-Pages: <int>`
  - `X-Process-Time-Sec: <float>`
  - `X-Total-Tokens: <int>`
- **HTTP Body**:
  - Raw binary stream of the generated Microsoft Word `.docx` file.

#### Error Responses
- `400 Bad Request`: Empty body or corrupt/invalid PDF header.
- `413 Payload Too Large`: PDF size exceeds `MAX_FILE_SIZE_MB`.
- `502 Bad Gateway`: Upstream Qwen VLM API failure after retries.
- `500 Internal Server Error`: Unhandled server exception.

---

### 2. Health Check (`GET /health` or `GET /api/v1/health`)

#### Response (`200 OK`)
```json
{
  "status": "healthy",
  "service": "pdf-to-word-microservice",
  "model": "qwen3.7-flash",
  "render_dpi": 200,
  "max_concurrent_pages": 6,
  "api_key_configured": true
}
```

---

## Configuration Reference (`.env`)

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `DASHSCOPE_API_KEY` | `string` | *(Required)* | Alibaba Cloud DashScope API Key |
| `DASHSCOPE_BASE_URL` | `string` | Alibaba Singapore Endpoint | OpenAI-compatible endpoint base URL |
| `MODEL_NAME` | `string` | `qwen3.7-flash` | Target Vision-Language Model name |
| `RENDER_DPI` | `int` | `200` | PDF page rendering resolution (DPI) |
| `MAX_CONCURRENT_PAGES` | `int` | `6` | Max concurrent page requests per document |
| `MAX_FILE_SIZE_MB` | `int` | `50` | Maximum allowed upload size in Megabytes |
| `HOST` | `string` | `0.0.0.0` | Server listening host interface |
| `PORT` | `int` | `8000` | Server HTTP port |
| `LOG_LEVEL` | `string` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## Quick Start & Deployment

### Option A: Running Locally with Conda / Python

1. **Activate Python Environment**:
   ```bash
   conda activate ml
   # Or using standard virtual environment:
   # python -m venv .venv && source .venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   # From the pdf_to_word_service project root
   pip install -r requirements.txt
   ```

3. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your DASHSCOPE_API_KEY
   ```

4. **Start the Microservice**:
   ```bash
   fastapi run app/main.py --host 0.0.0.0 --port 8000
   ```
   *The interactive API documentation will be available at: http://localhost:8000/docs*

---

### Option B: Running with Docker / Docker Compose

1. **Build and Run with Docker Compose**:
   ```bash
   # From the pdf_to_word_service project root
   docker compose up --build -d
   ```

2. **Check Logs**:
   ```bash
   docker compose logs -f
   ```

3. **Stop Service**:
   ```bash
   docker compose down
   ```

---

## Running Automated Tests

Testing dependencies are isolated in `requirements-dev.txt`.

```bash
# From the pdf_to_word_service project root
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## Integration Examples

### cURL

```bash
curl -X POST "http://localhost:8000/api/v1/convert" \
     -H "Content-Type: application/pdf" \
     -H "Content-Disposition: filename=\"annual_report.pdf\"" \
     --data-binary "@./sample.pdf" \
     --output "annual_report.docx"
```

### Python (Pure Standard Library - Zero External Dependencies)

```python
import urllib.request
import urllib.parse

url = "http://localhost:8000/api/v1/convert"
pdf_path = "document.pdf"
output_docx_path = "output.docx"

with open(pdf_path, "rb") as f:
    pdf_data = f.read()

quoted_name = urllib.parse.quote(pdf_path)
headers = {
    "Content-Type": "application/pdf",
    "Content-Disposition": f"filename=\"{quoted_name}\"; filename*=UTF-8''{quoted_name}"
}

req = urllib.request.Request(url, data=pdf_data, headers=headers, method="POST")

with urllib.request.urlopen(req) as response:
    docx_data = response.read()
    with open(output_docx_path, "wb") as out_f:
        out_f.write(docx_data)

print(f"Successfully saved converted document to {output_docx_path}")
```

### Node.js / JavaScript (Fetch API)

```javascript
import fs from 'fs';

async function convertPdfToDocx(pdfFilePath, outputDocxPath) {
  const pdfBuffer = fs.readFileSync(pdfFilePath);

  const response = await fetch('http://localhost:8000/api/v1/convert', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/pdf',
      'Content-Disposition': `filename="${pdfFilePath}"`
    },
    body: pdfBuffer
  });

  if (!response.ok) {
    throw new Error(`HTTP Error ${response.status}: ${await response.text()}`);
  }

  const docxArrayBuffer = await response.arrayBuffer();
  fs.writeFileSync(outputDocxPath, Buffer.from(docxArrayBuffer));
  console.log(`Converted file saved to: ${outputDocxPath}`);
}

convertPdfToDocx('invoice.pdf', 'invoice.docx');
```

---

## License & Support
Internal Team Microservice for JumboOCR. For questions or enterprise handover, please consult the team documentation.
