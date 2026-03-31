"""
Sales IQ - OCR Agent
Document intelligence agent using open-source OCR for extracting
structured data from invoices, receipts, and credit notes.
Uses PyPDF2/pdfplumber for PDFs and Pillow for image pre-processing.
Falls back gracefully when optional OCR engines aren't installed.
"""

import io
import os
import re
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, PipelineStage, AgentContext
from app.models.business import OCRDocument, Invoice, Customer


# ── OCR Engine Detection ─────────────────────────────────────────────

def _detect_ocr_engine() -> str:
    """Detect which OCR engine is available."""
    try:
        import easyocr  # noqa
        return "easyocr"
    except ImportError:
        pass
    try:
        import pytesseract  # noqa
        return "pytesseract"
    except ImportError:
        pass
    return "pdf_text_only"


OCR_ENGINE = _detect_ocr_engine()


# ── Stage 1: Document Intake ─────────────────────────────────────────

class DocumentIntakeStage(PipelineStage):
    """Accept and classify uploaded documents."""

    name = "document_intake"

    SUPPORTED_TYPES = {
        "application/pdf": "pdf",
        "image/png": "image",
        "image/jpeg": "image",
        "image/jpg": "image",
        "image/tiff": "image",
    }

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        # Get documents pending processing
        result = await db.execute(
            select(OCRDocument).where(
                OCRDocument.tenant_id == ctx.tenant_id,
                OCRDocument.processing_status == "pending",
            ).limit(50)
        )
        documents = result.scalars().all()
        ctx.records_processed = len(documents)

        if not documents:
            ctx.extra["no_documents"] = True
            return

        for doc in documents:
            did = str(doc.id)
            ctx.get_entity_result(did)
            er = ctx.entity_results[did]
            er["document"] = doc

            # Classify document type from filename
            fname = (doc.file_name or "").lower()
            if any(kw in fname for kw in ["invoice", "inv", "sinv", "sales_invoice", "فاتورة"]):
                doc.document_type = "invoice"
            elif any(kw in fname for kw in ["receipt", "payment", "remittance", "إيصال"]):
                doc.document_type = "payment_advice"
            elif any(kw in fname for kw in ["credit", "cn", "credit_note"]):
                doc.document_type = "credit_note"
            elif any(kw in fname for kw in ["po", "purchase_order", "order"]):
                doc.document_type = "purchase_order"
            else:
                doc.document_type = doc.document_type or "invoice"  # Default

            doc.processing_status = "processing"
            er["doc_type"] = doc.document_type

        await db.flush()
        ctx.extra["ocr_engine"] = OCR_ENGINE
        ctx.extra["documents_queued"] = len(documents)


# ── Stage 2: Text Extraction ─────────────────────────────────────────

class TextExtractionStage(PipelineStage):
    """OCR processing: extract text from PDF/image documents."""

    name = "text_extraction"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        extracted_count = 0

        for entity_id, er in ctx.entity_results.items():
            doc = er.get("document")
            if not doc:
                continue

            text = ""
            confidence = 0.0
            file_path = doc.file_path or ""

            try:
                mime = doc.mime_type or ""

                if "pdf" in mime or file_path.lower().endswith(".pdf"):
                    text, confidence = await self._extract_pdf(file_path)
                elif any(ext in file_path.lower() for ext in [".png", ".jpg", ".jpeg", ".tiff"]):
                    text, confidence = await self._extract_image(file_path)
                else:
                    # Try PDF first, then image
                    text, confidence = await self._extract_pdf(file_path)
                    if not text.strip():
                        text, confidence = await self._extract_image(file_path)

                if text.strip():
                    er["extracted_text"] = text
                    er["extraction_confidence"] = confidence
                    extracted_count += 1
                    ctx.records_succeeded += 1
                else:
                    doc.processing_status = "failed"
                    doc.error_message = "No text could be extracted from document"
                    ctx.add_issue(entity_id, "text_extraction", "critical",
                                  "empty_extraction", "No text extracted from document")
                    ctx.records_failed += 1

            except Exception as e:
                doc.processing_status = "failed"
                doc.error_message = str(e)[:500]
                ctx.add_issue(entity_id, "text_extraction", "critical",
                              "extraction_error", f"OCR failed: {str(e)[:200]}")
                ctx.records_failed += 1

        ctx.extra["texts_extracted"] = extracted_count
        await db.flush()

    async def _extract_pdf(self, file_path: str) -> tuple:
        """Extract text from PDF using pdfplumber (preferred) or PyPDF2."""
        text = ""
        confidence = 0.0

        if not os.path.exists(file_path):
            return text, confidence

        # Try pdfplumber first (better table extraction)
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                pages_text = []
                for page in pdf.pages[:20]:  # Limit to 20 pages
                    page_text = page.extract_text() or ""
                    # Also try tables
                    tables = page.extract_tables() or []
                    for table in tables:
                        for row in table:
                            if row:
                                page_text += "\n" + "\t".join(str(c or "") for c in row)
                    pages_text.append(page_text)
                text = "\n\n".join(pages_text)
                confidence = 0.85 if text.strip() else 0.0
                return text, confidence
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback to PyPDF2
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            pages_text = []
            for page in reader.pages[:20]:
                pages_text.append(page.extract_text() or "")
            text = "\n\n".join(pages_text)
            confidence = 0.75 if text.strip() else 0.0
        except ImportError:
            pass
        except Exception:
            pass

        return text, confidence

    async def _extract_image(self, file_path: str) -> tuple:
        """Extract text from image using available OCR engine."""
        if not os.path.exists(file_path):
            return "", 0.0

        if OCR_ENGINE == "easyocr":
            return await self._ocr_easyocr(file_path)
        elif OCR_ENGINE == "pytesseract":
            return await self._ocr_pytesseract(file_path)
        else:
            return "", 0.0

    async def _ocr_easyocr(self, file_path: str) -> tuple:
        """Use EasyOCR for text extraction."""
        try:
            import easyocr
            reader = easyocr.Reader(["en", "ar"], gpu=False)
            results = reader.readtext(file_path)
            text_parts = []
            confidences = []
            for (bbox, text, conf) in results:
                text_parts.append(text)
                confidences.append(conf)
            text = "\n".join(text_parts)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            return text, avg_conf
        except Exception as e:
            return f"[EasyOCR error: {e}]", 0.0

    async def _ocr_pytesseract(self, file_path: str) -> tuple:
        """Use pytesseract for text extraction."""
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img, lang="eng+ara")
            # Tesseract doesn't give per-word confidence easily
            confidence = 0.70 if text.strip() else 0.0
            return text, confidence
        except Exception as e:
            return f"[Tesseract error: {e}]", 0.0


# ── Stage 3: Field Mapping ───────────────────────────────────────────

class FieldMappingStage(PipelineStage):
    """Map extracted text to invoice/payment fields using regex patterns."""

    name = "field_mapping"

    # Regex patterns for common invoice fields
    PATTERNS = {
        "invoice_number": [
            r"(?:Invoice|Inv|Tax Invoice|فاتورة)[#:\s]*([A-Z0-9/-]{3,20})",
            r"(?:Document|Doc)[#:\s]*([A-Z0-9/-]{3,20})",
            r"(?:SINV|INV|SI)[/-]?\s*(\d{3,})",
        ],
        "invoice_date": [
            r"(?:Invoice Date|Date|التاريخ)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(?:Date)[:\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        ],
        "due_date": [
            r"(?:Due Date|Payment Due|تاريخ الاستحقاق)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        ],
        "total_amount": [
            r"(?:Total|Grand Total|Net Total|Amount Due|المبلغ الإجمالي)[:\s]*([A-Z]{3})?\s*([\d,]+\.?\d*)",
            r"(?:Total)[:\s]*([\d,]+\.?\d{2})",
        ],
        "tax_amount": [
            r"(?:VAT|Tax|ضريبة)[:\s]*(?:[A-Z]{3})?\s*([\d,]+\.?\d*)",
            r"(?:VAT\s*\(?\s*\d+%?\s*\)?)[:\s]*([\d,]+\.?\d*)",
        ],
        "currency": [
            r"\b(AED|SAR|QAR|BHD|KWD|OMR|USD|EUR|GBP)\b",
        ],
        "customer_name": [
            r"(?:Bill To|Customer|Client|العميل)[:\s]*([A-Za-z\s&.,]{3,50})",
            r"(?:Sold To|Attention)[:\s]*([A-Za-z\s&.,]{3,50})",
        ],
        "trn": [
            r"(?:TRN|Tax Reg|VAT No|الرقم الضريبي)[:\s]*(\d{15})",
        ],
        "po_number": [
            r"(?:PO|Purchase Order|P\.O\.)[#:\s]*([A-Z0-9/-]{3,20})",
        ],
    }

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        mapped_count = 0

        for entity_id, er in ctx.entity_results.items():
            doc = er.get("document")
            text = er.get("extracted_text", "")
            if not doc or not text:
                continue

            extracted = {}
            confidences = {}

            for field, patterns in self.PATTERNS.items():
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                    if match:
                        value = match.group(match.lastindex or 1).strip()
                        if value and field not in extracted:
                            extracted[field] = value
                            confidences[field] = er.get("extraction_confidence", 0.7)
                            break

            # Clean and normalize extracted values
            if "total_amount" in extracted:
                amt_str = extracted["total_amount"].replace(",", "")
                try:
                    extracted["total_amount"] = float(amt_str)
                except ValueError:
                    pass

            if "tax_amount" in extracted:
                tax_str = extracted["tax_amount"].replace(",", "")
                try:
                    extracted["tax_amount"] = float(tax_str)
                except ValueError:
                    pass

            doc.extracted_fields = extracted
            doc.confidence_scores = confidences
            doc.overall_confidence = (
                sum(confidences.values()) / len(confidences) if confidences else 0
            )

            er["extracted_fields"] = extracted
            er["field_count"] = len(extracted)

            if extracted:
                mapped_count += 1

        ctx.extra["fields_mapped"] = mapped_count
        await db.flush()


# ── Stage 4: Validation ─────────────────────────────────────────────

class OCRValidationStage(PipelineStage):
    """Cross-check extracted values against business rules."""

    name = "validation"

    async def process(self, db: AsyncSession, ctx: AgentContext) -> None:
        validated_count = 0

        for entity_id, er in ctx.entity_results.items():
            doc = er.get("document")
            fields = er.get("extracted_fields", {})
            if not doc or not fields:
                continue

            needs_review = False
            validation_notes = []

            # Check critical fields
            required = ["invoice_number"] if doc.document_type == "invoice" else []
            for req in required:
                if req not in fields:
                    needs_review = True
                    validation_notes.append(f"Missing required field: {req}")
                    ctx.add_issue(entity_id, "validation", "warning",
                                  req, f"Required field '{req}' not extracted")

            # Validate amounts
            total = fields.get("total_amount")
            if total and isinstance(total, (int, float)):
                if total <= 0:
                    needs_review = True
                    validation_notes.append("Total amount is zero or negative")
                    ctx.add_issue(entity_id, "validation", "warning",
                                  "total_amount", "Extracted amount is zero or negative")
                elif total > 10_000_000:
                    needs_review = True
                    validation_notes.append(f"Unusually large amount: {total:,.2f}")
                    ctx.add_issue(entity_id, "validation", "info",
                                  "total_amount", f"Unusually large amount: {total:,.2f}")

            # Validate invoice number format
            inv_num = fields.get("invoice_number", "")
            if inv_num and len(inv_num) < 3:
                needs_review = True
                validation_notes.append(f"Invoice number too short: {inv_num}")

            # Check for duplicate invoice number
            if inv_num:
                dup_result = await db.execute(
                    select(Invoice).where(
                        Invoice.tenant_id == ctx.tenant_id,
                        Invoice.invoice_number == inv_num,
                    )
                )
                if dup_result.scalar_one_or_none():
                    needs_review = True
                    validation_notes.append(f"Invoice {inv_num} already exists in system")
                    ctx.add_issue(entity_id, "validation", "warning",
                                  "invoice_number", f"Duplicate invoice number: {inv_num}")

            # Check confidence
            overall_conf = doc.overall_confidence or 0
            if overall_conf < 0.6:
                needs_review = True
                validation_notes.append(f"Low extraction confidence: {overall_conf:.0%}")

            doc.needs_review = needs_review
            doc.processing_status = "completed" if not needs_review else "needs_review"
            doc.processed_at = datetime.now(timezone.utc).isoformat()

            er["needs_review"] = needs_review
            er["validation_notes"] = validation_notes
            validated_count += 1

        ctx.extra["validated"] = validated_count
        await db.flush()


# ── Agent ─────────────────────────────────────────────────────────────

class OCRAgent(BaseAgent):
    """Document intelligence agent with open-source OCR."""

    agent_name = "ocr_agent"
    stages = [
        DocumentIntakeStage(),
        TextExtractionStage(),
        FieldMappingStage(),
        OCRValidationStage(),
    ]


# Singleton
ocr_agent = OCRAgent()
