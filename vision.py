import base64

import cv2
import numpy as np


def load_image(contents: bytes) -> np.ndarray:
    """Decode uploaded bytes into an OpenCV image."""
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image format. Please upload a valid image.")
    return img


def preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    """Convert to grayscale and apply Otsu thresholding."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def encode_png_base64(img: np.ndarray) -> str:
    """Encode an image as a base64 PNG string."""
    _, buffer = cv2.imencode(".png", img)
    return base64.b64encode(buffer).decode("utf-8")
