import os

import pytesseract

# Tesseract isn't on PATH by default in this Windows install; pin the known binary.
_tesseract_bin = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_tesseract_bin):
    pytesseract.pytesseract.tesseract_cmd = _tesseract_bin


def extract_text_and_confidence(thresh) -> tuple[str, float]:
    """Run Tesseract OCR and return assembled text + average confidence."""
    ocr_data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)

    texts = []
    confidences = []

    for i in range(len(ocr_data["text"])):
        text = ocr_data["text"][i].strip()
        conf = int(ocr_data["conf"][i])

        # Tesseract returns -1 for empty spaces, so we filter those out
        if text and conf > -1:
            texts.append(text)
            confidences.append(conf)

    detected_text = " ".join(texts)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    if not detected_text:
        detected_text = "No text detected."

    return detected_text, avg_confidence
