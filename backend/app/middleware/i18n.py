"""
Sales IQ - Internationalization (i18n) Middleware
Day 19: Accept-Language header parsing, locale resolution, RTL support.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ═══════════════════════════════════════════
# Supported locales
# ═══════════════════════════════════════════

SUPPORTED_LOCALES = {
    "en": {
        "code": "en",
        "name": "English",
        "native_name": "English",
        "direction": "ltr",
        "date_format": "YYYY-MM-DD",
        "number_decimal": ".",
        "number_thousands": ",",
        "currency_position": "before",
        "default_currency": "USD",
    },
    "ar": {
        "code": "ar",
        "name": "Arabic",
        "native_name": "العربية",
        "direction": "rtl",
        "date_format": "DD/MM/YYYY",
        "number_decimal": "٫",
        "number_thousands": "٬",
        "currency_position": "after",
        "default_currency": "SAR",
    },
}

DEFAULT_LOCALE = "en"
RTL_LOCALES = {"ar", "he", "fa", "ur"}


def parse_accept_language(header: str) -> str:
    """
    Parse Accept-Language header and return the best matching locale.

    Examples:
        'ar-SA,ar;q=0.9,en;q=0.8' -> 'ar'
        'en-US,en;q=0.9' -> 'en'
        'fr-FR,fr;q=0.9' -> 'en' (fallback)
    """
    if not header:
        return DEFAULT_LOCALE

    # Parse quality-weighted language tags
    langs = []
    for part in header.split(","):
        part = part.strip()
        if ";q=" in part:
            tag, q = part.split(";q=")
            try:
                langs.append((tag.strip(), float(q)))
            except ValueError:
                langs.append((tag.strip(), 0.0))
        else:
            langs.append((part.strip(), 1.0))

    # Sort by quality descending
    langs.sort(key=lambda x: x[1], reverse=True)

    # Match against supported locales
    for tag, _ in langs:
        # Exact match
        code = tag.lower()
        if code in SUPPORTED_LOCALES:
            return code
        # Language-only match (e.g., 'ar-SA' -> 'ar')
        base = code.split("-")[0]
        if base in SUPPORTED_LOCALES:
            return base

    return DEFAULT_LOCALE


class I18nMiddleware(BaseHTTPMiddleware):
    """
    Middleware that resolves locale from:
    1. ?lang= query parameter (highest priority)
    2. Accept-Language header
    3. User preference (from JWT)
    4. Default (en)

    Sets request.state.locale and adds response headers:
    - Content-Language: resolved locale
    - X-Text-Direction: ltr or rtl
    """

    async def dispatch(self, request: Request, call_next):
        # 1. Query parameter override
        locale = request.query_params.get("lang")

        # 2. Accept-Language header
        if not locale or locale not in SUPPORTED_LOCALES:
            accept_lang = request.headers.get("accept-language", "")
            locale = parse_accept_language(accept_lang)

        # Validate
        if locale not in SUPPORTED_LOCALES:
            locale = DEFAULT_LOCALE

        locale_info = SUPPORTED_LOCALES[locale]

        # Enrich request state
        request.state.locale = locale
        request.state.text_direction = locale_info["direction"]
        request.state.is_rtl = locale_info["direction"] == "rtl"
        request.state.locale_info = locale_info

        # Process request
        response = await call_next(request)

        # Add locale headers
        response.headers["Content-Language"] = locale
        response.headers["X-Text-Direction"] = locale_info["direction"]

        return response
