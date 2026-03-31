"""
Sales IQ - Locale / i18n Endpoints
Day 19: Supported locales, RTL configuration, UI translation bundles.
"""

from fastapi import APIRouter, Depends, Request

from app.core.deps import get_current_user
from app.models.core import User
from app.middleware.i18n import SUPPORTED_LOCALES, DEFAULT_LOCALE
from app.schemas.locale import (
    LocaleInfo, SupportedLocalesResponse,
    RTLConfig, LocaleConfigResponse,
    TranslationBundle, TranslationBundleListResponse,
)

router = APIRouter()


# ═══════════════════════════════════════════
# RTL layout configs per locale
# ═══════════════════════════════════════════

RTL_CONFIGS = {
    "en": RTLConfig(
        is_rtl=False, direction="ltr", text_align="left",
        sidebar_position="left", table_column_order="ltr",
        chart_axis_direction="left-to-right",
        number_display="western", calendar_type="gregorian",
    ),
    "ar": RTLConfig(
        is_rtl=True, direction="rtl", text_align="right",
        sidebar_position="right", table_column_order="rtl",
        chart_axis_direction="right-to-left",
        number_display="arabic-indic", calendar_type="hijri",
    ),
}

# ═══════════════════════════════════════════
# GCC Currencies
# ═══════════════════════════════════════════

GCC_CURRENCIES = ["SAR", "AED", "BHD", "KWD", "OMR", "QAR", "USD", "EUR", "GBP"]

# ═══════════════════════════════════════════
# Translation bundles (API-side labels)
# ═══════════════════════════════════════════

TRANSLATIONS = {
    "en": {
        "common": {
            "app_name": "Sales IQ",
            "welcome": "Welcome",
            "logout": "Log Out",
            "settings": "Settings",
            "search": "Search",
            "save": "Save",
            "cancel": "Cancel",
            "delete": "Delete",
            "edit": "Edit",
            "back": "Back",
            "loading": "Loading...",
            "no_data": "No data available",
            "error": "Something went wrong",
            "retry": "Retry",
            "confirm": "Confirm",
            "total": "Total",
            "page": "Page",
            "of": "of",
            "items": "items",
            "export_csv": "Export CSV",
            "apply_filters": "Apply Filters",
            "clear_filters": "Clear Filters",
        },
        "dashboard": {
            "total_ar": "Total AR Outstanding",
            "avg_dso": "Average DSO",
            "collection_rate": "Collection Rate",
            "overdue_amount": "Overdue Amount",
            "cash_forecast": "Cash Flow Forecast",
            "aging_chart": "Aging Analysis",
            "top_overdue": "Top Overdue Customers",
            "health_distribution": "Health Distribution",
            "kpi_cards": "Key Performance Indicators",
            "trend_7d": "7-Day Trend",
            "trend_30d": "30-Day Trend",
        },
        "customers": {
            "customer_list": "Customer List",
            "customer_360": "Customer 360",
            "health_score": "Health Score",
            "credit_limit": "Credit Limit",
            "credit_utilized": "Credit Utilized",
            "risk_level": "Risk Level",
            "segment": "Segment",
            "territory": "Territory",
            "last_payment": "Last Payment",
            "outstanding": "Outstanding Balance",
            "overdue": "Overdue Balance",
        },
        "collections": {
            "worklist": "Collections Worklist",
            "priority_score": "Priority Score",
            "promise_to_pay": "Promise to Pay",
            "escalation": "Escalation",
            "dispute": "Dispute",
            "log_call": "Log Call",
            "log_email": "Log Email",
            "ai_draft": "AI Draft Message",
            "case_status": "Case Status",
        },
        "intelligence": {
            "ai_briefing": "AI Briefing",
            "predictions": "Predictions",
            "chat": "AI Chat",
            "churn_risk": "Churn Risk",
            "payment_prediction": "Payment Prediction",
            "recommended_action": "Recommended Action",
        },
        "admin": {
            "user_management": "User Management",
            "business_rules": "Business Rules",
            "system_health": "System Health",
            "audit_log": "Audit Log",
            "agent_hub": "Agent Hub",
            "demo_data": "Demo Data Manager",
        },
    },
    "ar": {
        "common": {
            "app_name": "سيلز آي كيو",
            "welcome": "مرحباً",
            "logout": "تسجيل الخروج",
            "settings": "الإعدادات",
            "search": "بحث",
            "save": "حفظ",
            "cancel": "إلغاء",
            "delete": "حذف",
            "edit": "تعديل",
            "back": "رجوع",
            "loading": "جاري التحميل...",
            "no_data": "لا توجد بيانات",
            "error": "حدث خطأ",
            "retry": "إعادة المحاولة",
            "confirm": "تأكيد",
            "total": "الإجمالي",
            "page": "صفحة",
            "of": "من",
            "items": "عناصر",
            "export_csv": "تصدير CSV",
            "apply_filters": "تطبيق الفلاتر",
            "clear_filters": "مسح الفلاتر",
        },
        "dashboard": {
            "total_ar": "إجمالي المستحقات",
            "avg_dso": "متوسط أيام التحصيل",
            "collection_rate": "نسبة التحصيل",
            "overdue_amount": "المبالغ المتأخرة",
            "cash_forecast": "توقعات التدفق النقدي",
            "aging_chart": "تحليل التقادم",
            "top_overdue": "أكبر العملاء المتأخرين",
            "health_distribution": "توزيع الصحة المالية",
            "kpi_cards": "مؤشرات الأداء الرئيسية",
            "trend_7d": "اتجاه ٧ أيام",
            "trend_30d": "اتجاه ٣٠ يوم",
        },
        "customers": {
            "customer_list": "قائمة العملاء",
            "customer_360": "ملف العميل الشامل",
            "health_score": "درجة الصحة المالية",
            "credit_limit": "حد الائتمان",
            "credit_utilized": "الائتمان المستخدم",
            "risk_level": "مستوى المخاطر",
            "segment": "الشريحة",
            "territory": "المنطقة",
            "last_payment": "آخر دفعة",
            "outstanding": "الرصيد المستحق",
            "overdue": "الرصيد المتأخر",
        },
        "collections": {
            "worklist": "قائمة التحصيل",
            "priority_score": "درجة الأولوية",
            "promise_to_pay": "وعد بالدفع",
            "escalation": "تصعيد",
            "dispute": "نزاع",
            "log_call": "تسجيل مكالمة",
            "log_email": "تسجيل بريد",
            "ai_draft": "مسودة الذكاء الاصطناعي",
            "case_status": "حالة القضية",
        },
        "intelligence": {
            "ai_briefing": "ملخص الذكاء الاصطناعي",
            "predictions": "التنبؤات",
            "chat": "محادثة ذكية",
            "churn_risk": "مخاطر فقدان العميل",
            "payment_prediction": "توقع الدفع",
            "recommended_action": "الإجراء الموصى به",
        },
        "admin": {
            "user_management": "إدارة المستخدمين",
            "business_rules": "قواعد العمل",
            "system_health": "صحة النظام",
            "audit_log": "سجل المراجعة",
            "agent_hub": "مركز الوكلاء",
            "demo_data": "مدير البيانات التجريبية",
        },
    },
}


# ═══════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════

@router.get("/locales", response_model=SupportedLocalesResponse)
async def get_supported_locales(request: Request):
    """List all supported locales with metadata."""
    current = getattr(request.state, "locale", DEFAULT_LOCALE)
    locales = [LocaleInfo(**info) for info in SUPPORTED_LOCALES.values()]
    return SupportedLocalesResponse(
        locales=locales, default=DEFAULT_LOCALE, current=current,
    )


@router.get("/locales/{locale_code}/config", response_model=LocaleConfigResponse)
async def get_locale_config(
    locale_code: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Get full locale + RTL configuration bundle for a specific locale."""
    if locale_code not in SUPPORTED_LOCALES:
        from fastapi import HTTPException
        raise HTTPException(404, f"Locale '{locale_code}' not supported")

    locale_info = LocaleInfo(**SUPPORTED_LOCALES[locale_code])
    rtl_config = RTL_CONFIGS.get(locale_code, RTL_CONFIGS["en"])

    # Get user timezone preference
    user_prefs = current_user.preferences or {}
    tz = user_prefs.get("timezone", "Asia/Dubai")

    return LocaleConfigResponse(
        locale=locale_info,
        rtl=rtl_config,
        supported_currencies=GCC_CURRENCIES,
        timezone=tz,
    )


@router.get("/locales/{locale_code}/translations", response_model=TranslationBundleListResponse)
async def get_translations(locale_code: str):
    """Get all UI translation bundles for a locale."""
    if locale_code not in TRANSLATIONS:
        from fastapi import HTTPException
        raise HTTPException(404, f"Translations not available for '{locale_code}'")

    locale_translations = TRANSLATIONS[locale_code]
    bundles = [
        TranslationBundle(locale=locale_code, namespace=ns, translations=trans)
        for ns, trans in locale_translations.items()
    ]

    return TranslationBundleListResponse(
        locale=locale_code,
        namespaces=list(locale_translations.keys()),
        bundles=bundles,
    )


@router.get("/locales/{locale_code}/translations/{namespace}", response_model=TranslationBundle)
async def get_translation_namespace(locale_code: str, namespace: str):
    """Get translation bundle for a specific namespace."""
    if locale_code not in TRANSLATIONS:
        from fastapi import HTTPException
        raise HTTPException(404, f"Translations not available for '{locale_code}'")

    locale_translations = TRANSLATIONS[locale_code]
    if namespace not in locale_translations:
        from fastapi import HTTPException
        raise HTTPException(404, f"Namespace '{namespace}' not found for locale '{locale_code}'")

    return TranslationBundle(
        locale=locale_code,
        namespace=namespace,
        translations=locale_translations[namespace],
    )
