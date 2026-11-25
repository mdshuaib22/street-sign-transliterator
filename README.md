# SignLens — Street Sign Translator

Real-time street sign OCR and translation. Python FastAPI backend + light-themed frontend.

## Run on Linux/Mac

```bash
# Step 1: Install Tesseract
sudo apt install tesseract-ocr -y        # Ubuntu/Linux
# brew install tesseract                 # Mac

# Step 2: Run the app
bash run.sh

# Step 3: Open browser
# http://localhost:8000
```

## Run on Windows

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Then open http://localhost:8000

## Languages
Kannada · Telugu · Tamil · Marathi · Malayalam · Hindi · English · French · Spanish · Arabic

## Stack
- Python 3.10+ · FastAPI · Tesseract OCR · OpenCV · deep-translator

## Configuration

- `MAX_UPLOAD_BYTES` — upload limit in bytes (default 10485760). Over-limit requests get 413.
- `TRANSLATION_TIMEOUT` — seconds allowed for the translation upstream (default 15). Timeouts return 504, failures 503.
- `ALLOWED_ORIGINS` — comma-separated list of origins allowed to call the API from a browser. Empty by default: the app is same-origin, and no wildcard-with-credentials CORS is opened.

## Tests and CI

```bash
pip install -r requirements.txt
python -m pytest -q
```

GitHub Actions runs a syntax check and the test suite on every push and pull request to `main`.

## Access control

There is no login screen and no authentication: anyone who can reach the server can use the OCR and translation endpoints, which spend upstream translation calls. Run it on localhost, or put it behind a VPN or an authenticating reverse proxy before exposing it publicly.
