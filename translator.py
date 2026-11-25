from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from deep_translator import GoogleTranslator


class TranslationError(Exception):
    """The translation upstream could not produce a result."""


class TranslationTimeoutError(TranslationError):
    """The translation upstream exceeded the caller's budget."""


_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="translator")


def translate_text(detected_text: str, language: str, timeout: float | None = None) -> str:
    """Translate detected text to the requested language code.

    `timeout` is seconds; the underlying client has no timeout of its own, so
    the call runs in a bounded worker and a timeout becomes a typed error
    instead of a fake success string.
    """
    if language == "en" or detected_text == "No text detected.":
        return detected_text

    def call():
        translator = GoogleTranslator(source="auto", target=language)
        return translator.translate(detected_text)

    try:
        if timeout is None:
            return call()
        return _executor.submit(call).result(timeout=timeout)
    except FutureTimeoutError as exc:
        raise TranslationTimeoutError(
            f"Translation timed out after {timeout}s."
        ) from exc
    except Exception as exc:
        raise TranslationError("Translation service unavailable.") from exc

