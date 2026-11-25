import os
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from ocr import extract_text_and_confidence
from translator import TranslationError, TranslationTimeoutError, translate_text
from vision import encode_png_base64, load_image, preprocess_for_ocr

# Project root, so index.html is found regardless of the working directory
# uvicorn / Docker run from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
TRANSLATION_TIMEOUT = float(os.getenv("TRANSLATION_TIMEOUT", "15"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
SUPPORTED_LANGUAGES = {"en", "kn", "te", "ta", "mr", "ml", "hi", "fr", "es", "ar"}

app = FastAPI(title="SignLens Translation API")

# Same-origin by default: the frontend is served from / by this app. Cross-origin
# access is opt-in through ALLOWED_ORIGINS, never a wildcard with credentials.
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


class ApiError(Exception):
    """A failure with a stable machine code, mapped to the shared error envelope."""

    def __init__(self, status, code, message, field_errors=None, retryable=False,
                 retry_after=None, extra=None):
        self.status = status
        self.code = code
        self.message = message
        self.field_errors = field_errors or []
        self.retryable = retryable
        self.retry_after = retry_after
        self.extra = extra or {}
        super().__init__(message)


def _request_id(request):
    return getattr(request.state, "request_id", None)


def _success(data, request):
    payload = dict(data)
    payload.setdefault("version", 1)
    payload.setdefault("status", "ok")
    payload.setdefault("request_id", _request_id(request))
    return payload


def _error(request, status, code, message, field_errors=None, retryable=False,
           retry_after=None, extra=None):
    body = {
        # `detail` is kept for the deployed frontend, which reads it on errors.
        "detail": message,
        "version": 1,
        "request_id": _request_id(request),
        "error": {
            "code": code,
            "message": message,
            "field_errors": field_errors or [],
            "retryable": retryable,
        },
    }
    if extra:
        body.update(extra)
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(status_code=status, content=body, headers=headers)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    try:
        response = await call_next(request)
    except Exception:
        # Log the traceback server-side; never return exception text to a caller.
        import logging
        logging.exception("Unhandled error for %s %s", request.method, request.url.path)
        response = _error(request, 500, "internal_error", "An internal error occurred.")
    response.headers["X-Request-ID"] = _request_id(request) or ""
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return _error(request, exc.status, exc.code, exc.message,
                  field_errors=exc.field_errors, retryable=exc.retryable,
                  retry_after=exc.retry_after, extra=exc.extra)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    fields = [
        {"field": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return _error(request, 422, "validation_error", "Invalid request.", field_errors=fields)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return _error(request, exc.status_code, "http_error", str(exc.detail))


@app.get("/api/health")
def health_check(request: Request):
    """Endpoint the frontend polls to confirm the backend is online."""
    return _success({"status": "ok"}, request)


@app.post("/api/upload-image")
async def process_image(request: Request, file: UploadFile = File(...),
                        language: str = Form("en")):
    """Handle image upload, preprocessing, OCR, and translation."""
    target = language.strip().lower()
    if target not in SUPPORTED_LANGUAGES:
        raise ApiError(
            422,
            "unsupported_language",
            "Unsupported target language.",
            field_errors=[{"field": "language", "message": "Choose a supported language code."}],
            extra={"supported_languages": sorted(SUPPORTED_LANGUAGES)},
        )

    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise ApiError(
            413,
            "payload_too_large",
            "The uploaded image is too large.",
            field_errors=[{"field": "file", "message": "Use a smaller image."}],
            extra={"limit_bytes": MAX_UPLOAD_BYTES},
        )
    if not contents:
        raise ApiError(
            422,
            "invalid_image",
            "The uploaded file is empty.",
            field_errors=[{"field": "file", "message": "Choose an image with content."}],
        )

    try:
        img = load_image(contents)
    except ValueError as exc:
        raise ApiError(
            422,
            "invalid_image",
            str(exc),
            field_errors=[{"field": "file", "message": str(exc)}],
        )

    thresh = preprocess_for_ocr(img)

    try:
        detected_text, avg_confidence = extract_text_and_confidence(thresh)
    except Exception:
        raise ApiError(
            503,
            "ocr_unavailable",
            "The OCR service is unavailable.",
            retryable=True,
            retry_after=5,
        )

    no_text = detected_text == "No text detected."
    if target == "en" or no_text:
        translated_text = detected_text
    else:
        try:
            translated_text = translate_text(detected_text, target, timeout=TRANSLATION_TIMEOUT)
        except TranslationTimeoutError:
            raise ApiError(
                504,
                "upstream_timeout",
                "The translation service timed out.",
                retryable=True,
                retry_after=5,
            )
        except TranslationError:
            raise ApiError(
                503,
                "translation_unavailable",
                "The translation service is unavailable.",
                retryable=True,
                retry_after=10,
            )

    return _success({
        "confidence": round(avg_confidence, 1),
        "detected_text": detected_text,
        "translated_text": translated_text,
        "preprocessed_image": encode_png_base64(thresh),
        "status": "no_text" if no_text else "ok",
    }, request)


@app.get("/")
def serve_frontend():
    """Serve the self-contained frontend at / so http://localhost:8000 opens
    the app and /api/* calls share the same origin (no file:// or CORS issues)."""
    return FileResponse(str(os.path.join(BASE_DIR, "index.html")))
