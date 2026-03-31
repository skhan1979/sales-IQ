"""
Sales IQ - Locale / i18n Schemas
Day 19: Pydantic models for locale configuration, RTL support, and translations.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# ═══════════════════════════════════════════
# Locale Info
# ═══════════════════════════════════════════

class LocaleInfo(BaseModel):
    code: str
    name: str
    native_name: str
    direction: str  # "ltr" or "rtl"
    date_format: str
    number_decimal: str
    number_thousands: str
    currency_position: str
    default_currency: str


class SupportedLocalesResponse(BaseModel):
    locales: List[LocaleInfo]
    default: str
    current: str


# ═══════════════════════════════════════════
# RTL Configuration
# ═══════════════════════════════════════════

class RTLConfig(BaseModel):
    """Frontend RTL/layout configuration per locale."""
    is_rtl: bool
    direction: str
    text_align: str  # "left" or "right"
    sidebar_position: str  # "left" or "right"
    table_column_order: str  # "ltr" or "rtl"
    chart_axis_direction: str  # "left-to-right" or "right-to-left"
    number_display: str  # "western" or "arabic-indic"
    calendar_type: str  # "gregorian" or "hijri"


class LocaleConfigResponse(BaseModel):
    """Full locale + RTL configuration bundle for frontend."""
    locale: LocaleInfo
    rtl: RTLConfig
    supported_currencies: List[str]
    timezone: str


# ═══════════════════════════════════════════
# UI Translations (API label keys)
# ═══════════════════════════════════════════

class TranslationBundle(BaseModel):
    """Translation key-value pairs for a given namespace."""
    locale: str
    namespace: str
    translations: Dict[str, str]


class TranslationBundleListResponse(BaseModel):
    locale: str
    namespaces: List[str]
    bundles: List[TranslationBundle]


# ═══════════════════════════════════════════
# Standardized API Response Envelope
# ═══════════════════════════════════════════

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ResponseMeta(BaseModel):
    locale: str
    direction: str
    request_id: Optional[str] = None
    response_time_ms: Optional[int] = None
    pagination: Optional[PaginationMeta] = None


class APIEnvelopeResponse(BaseModel):
    """Standard response wrapper with metadata."""
    success: bool = True
    data: Any = None
    meta: Optional[ResponseMeta] = None
