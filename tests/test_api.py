import io

from PIL import Image
from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(language="en", content=None):
    return client.post(
        "/api/upload-image",
        files={"file": ("sign.png", png_bytes() if content is None else content, "image/png")},
        data={"language": language},
    )


def raising(exc):
    def fail(*args, **kwargs):
        raise exc
    return fail


def test_health_envelope():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == 1
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_root_serves_frontend():
    response = client.get("/")
    assert response.status_code == 200
    assert "Street Sign Translator" in response.text


def test_upload_success(monkeypatch):
    monkeypatch.setattr(main, "extract_text_and_confidence", lambda img: ("STOP", 92.5))
    monkeypatch.setattr(main, "translate_text", lambda text, lang, timeout=None: "STOP")
    response = upload("en")
    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == 92.5
    assert body["detected_text"] == "STOP"
    assert body["translated_text"] == "STOP"
    assert body["status"] == "ok"
    assert body["preprocessed_image"]


def test_translation_receives_bounded_timeout(monkeypatch):
    seen = {}

    def fake(text, lang, timeout=None):
        seen["timeout"] = timeout
        return "RARR"

    monkeypatch.setattr(main, "extract_text_and_confidence", lambda img: ("STOP", 80.0))
    monkeypatch.setattr(main, "translate_text", fake)
    response = upload("fr")
    assert response.status_code == 200
    assert seen["timeout"] == main.TRANSLATION_TIMEOUT


def test_no_text_is_explicit_status(monkeypatch):
    monkeypatch.setattr(main, "extract_text_and_confidence",
                        lambda img: ("No text detected.", 0.0))
    monkeypatch.setattr(main, "translate_text",
                        raising(AssertionError("should not call translation")))
    response = upload("fr")
    assert response.status_code == 200
    assert response.json()["status"] == "no_text"
    assert response.json()["translated_text"] == "No text detected."


def test_invalid_image_is_client_error():
    response = upload(content=b"not an image")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_image"
    assert body["error"]["field_errors"][0]["field"] == "file"
    assert body["detail"]


def test_empty_upload_is_client_error():
    response = upload(content=b"")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"


def test_unsupported_language():
    response = upload("xx")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "unsupported_language"
    assert "fr" in body["supported_languages"]


def test_missing_file_validation_error():
    response = client.post("/api/upload-image", data={"language": "en"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["field_errors"][0]["field"] == "file"


def test_translation_upstream_failure_is_503(monkeypatch):
    monkeypatch.setattr(main, "extract_text_and_confidence", lambda img: ("STOP", 80.0))
    monkeypatch.setattr(main, "translate_text", raising(main.TranslationError()))
    response = upload("fr")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "translation_unavailable"
    assert body["error"]["retryable"] is True
    assert response.headers["Retry-After"] == "10"


def test_translation_timeout_is_504(monkeypatch):
    monkeypatch.setattr(main, "extract_text_and_confidence", lambda img: ("STOP", 80.0))
    monkeypatch.setattr(main, "translate_text", raising(main.TranslationTimeoutError()))
    response = upload("fr")
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "upstream_timeout"
    assert response.headers["Retry-After"] == "5"


def test_ocr_failure_is_503(monkeypatch):
    monkeypatch.setattr(main, "extract_text_and_confidence",
                        raising(RuntimeError("tesseract exploded")))
    response = upload("en")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "ocr_unavailable"
    assert body["error"]["retryable"] is True
    assert "tesseract exploded" not in response.text


def test_payload_over_bound_is_413(monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 32)
    response = upload(content=b"x" * 64)
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "payload_too_large"
    assert body["limit_bytes"] == 32


def test_no_wildcard_cors_by_default():
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
