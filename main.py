import base64
import cv2
import numpy as np
import pytesseract
import os

# Tesseract isn't on PATH by default in this Windows install; pin the known binary.
_tesseract_bin = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_tesseract_bin):
    pytesseract.pytesseract.tesseract_cmd = _tesseract_bin

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from deep_translator import GoogleTranslator

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
        # 1. Read the uploaded file into a NumPy array
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image format. Please upload a valid image.")

        # 2. Preprocess the image to improve OCR accuracy
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply Otsu's thresholding to create a high-contrast black and white image
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 3. Perform OCR using Tesseract
        # We request dictionary output to access word-by-word confidence scores
        ocr_data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
        
        texts = []
        confidences = []
        
        for i in range(len(ocr_data['text'])):
            text = ocr_data['text'][i].strip()
            conf = int(ocr_data['conf'][i])
            
            # Tesseract returns -1 for empty spaces, so we filter those out
            if text and conf > -1:
                texts.append(text)
                confidences.append(conf)
                
        detected_text = " ".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        if not detected_text:
            detected_text = "No text detected."
            
        # 4. Translate the extracted text
        translated_text = detected_text
        if language != "en" and detected_text != "No text detected.":
            try:
                # deep-translator provides a stable, free bridge to Google Translate
                translator = GoogleTranslator(source='auto', target=language)
                translated_text = translator.translate(detected_text)
            except Exception as e:
                translated_text = f"[Translation Error] Could not connect to translation service."

        # 5. Encode the preprocessed image so the frontend can display what the OCR engine "saw"
        _, buffer = cv2.imencode('.png', thresh)
        preprocessed_b64 = base64.b64encode(buffer).decode('utf-8')

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