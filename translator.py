from deep_translator import GoogleTranslator


def translate_text(detected_text: str, language: str) -> str:
    """Translate detected text to the requested language code."""
    if language == "en" or detected_text == "No text detected.":
        return detected_text

    try:
        translator = GoogleTranslator(source="auto", target=language)
        return translator.translate(detected_text)
    except Exception:
        return "[Translation Error] Could not connect to translation service."
