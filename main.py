import os

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from vision import load_image, preprocess_for_ocr, encode_png_base64
from ocr import extract_text_and_confidence
from translator import translate_text

# Project root, so index.html is found regardless of the working directory
# uvicorn / Docker run from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="SignLens Translation API")

# Configure CORS so your HTML file can make requests to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace "*" with your frontend's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    """Endpoint the frontend polls to confirm the backend is online."""
    return {"status": "ok"}


@app.post("/api/upload-image")
async def process_image(
    file: UploadFile = File(...),
    language: str = Form("en")
):
    """Handles image upload, preprocessing, OCR, and translation."""
    try:
        # 1. Read the uploaded file into an OpenCV image
        contents = await file.read()
        img = load_image(contents)

        # 2. Preprocess the image to improve OCR accuracy
        thresh = preprocess_for_ocr(img)

        # 3. Perform OCR using Tesseract
        detected_text, avg_confidence = extract_text_and_confidence(thresh)

        # 4. Translate the extracted text
        translated_text = translate_text(detected_text, language)

        # 5. Encode the preprocessed image so the frontend can display what the OCR engine "saw"
        preprocessed_b64 = encode_png_base64(thresh)

        return {
            "confidence": round(avg_confidence, 1),
            "detected_text": detected_text,
            "translated_text": translated_text,
            "preprocessed_image": preprocessed_b64
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def serve_frontend():
    """Serve the self-contained frontend at / so http://localhost:8000 opens
    the app and /api/* calls share the same origin (no file:// or CORS issues)."""
    return FileResponse(str(os.path.join(BASE_DIR, "index.html")))
