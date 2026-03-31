"""
Sales IQ - Data Import API Endpoints
Upload, map, preview, and execute CSV/Excel imports with DQ integration.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole, AuditLog
from app.services.csv_import import (
    csv_parser, excel_parser, import_pipeline,
    ENTITY_FIELDS, HEADER_ALIASES,
)

router = APIRouter()

require_finance = RoleChecker(min_role=UserRole.FINANCE_MANAGER, allowed_roles=[UserRole.FINANCE_MANAGER])


# =============================================
# Schemas
# =============================================

class MappingOverride(BaseModel):
    """Manual field mapping overrides (csv_header -> entity_field)."""
    mapping: dict = Field(..., description="Dict of {csv_column: entity_field}")


class ImportExecuteRequest(BaseModel):
    """Execute an import with the given CSV content and mapping."""
    entity_type: str = Field(..., pattern="^(customers|invoices|payments|collections|disputes|credit_limits)$")
    csv_content: str = Field(..., description="Raw CSV content")
    mapping: dict = Field(..., description="Dict of {csv_column: entity_field}")
    skip_preview: bool = Field(False, description="Skip preview validation and import directly")


# =============================================
# Endpoints
# =============================================

@router.get("/fields/{entity_type}")
async def get_importable_fields(
    entity_type: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the list of importable fields for an entity type.
    Returns field definitions with type, required status, and description.
    """
    if entity_type not in ENTITY_FIELDS:
        raise HTTPException(400, f"Unknown entity type: {entity_type}. Choose from: {list(ENTITY_FIELDS.keys())}")

    fields = ENTITY_FIELDS[entity_type]
    return {
        "entity_type": entity_type,
        "fields": [
            {
                "name": name,
                "type": info[1],
                "required": info[2],
                "description": info[3],
            }
            for name, info in fields.items()
        ],
        "required_fields": [name for name, info in fields.items() if info[2]],
    }


@router.post("/upload-and-map")
async def upload_and_auto_map(
    entity_type: str = Form(..., pattern="^(customers|invoices|payments|collections|disputes|credit_limits)$"),
    file: UploadFile = File(...),
    current_user: User = Depends(require_finance),
):
    """
    Upload a CSV or Excel file and get auto-detected field mapping.
    Returns the parsed headers, suggested mapping, and sample rows.
    """
    if not file.filename:
        raise HTTPException(400, "No file provided")

    filename_lower = file.filename.lower()
    is_excel = filename_lower.endswith((".xlsx", ".xls"))
    is_csv = filename_lower.endswith(".csv")

    if not is_excel and not is_csv:
        raise HTTPException(400, "Unsupported file format. Please upload a CSV (.csv) or Excel (.xlsx, .xls) file.")

    # Read file content
    content = await file.read()

    if is_excel:
        # Parse Excel file
        headers, rows = excel_parser.parse(content)
    else:
        # Parse CSV file
        try:
            text = content.decode("utf-8-sig")  # Handle BOM
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        if not text.strip():
            raise HTTPException(400, "File is empty")

        headers, rows = csv_parser.parse(text)

    if not headers:
        raise HTTPException(400, "Could not detect column headers in the file")

    if not rows:
        raise HTTPException(400, "File contains headers but no data rows")

    # Auto-map
    mapping = csv_parser.auto_map(headers, entity_type)

    # Sample rows for frontend display
    sample = rows[:5] if rows else []

    # For CSV, include the raw text for subsequent calls; for Excel, re-serialize to CSV
    if is_excel:
        import csv as csv_mod
        import io as io_mod
        output = io_mod.StringIO()
        writer = csv_mod.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        csv_content = output.getvalue()
    else:
        csv_content = text

    return {
        "filename": file.filename,
        "entity_type": entity_type,
        "total_rows": len(rows),
        "headers": headers,
        "auto_mapping": mapping,
        "unmapped_headers": [h for h in headers if h not in mapping],
        "available_fields": list(ENTITY_FIELDS.get(entity_type, {}).keys()),
        "required_fields": [
            k for k, v in ENTITY_FIELDS.get(entity_type, {}).items() if v[2]
        ],
        "sample_rows": sample,
        "csv_content": csv_content,  # Return for subsequent preview/execute calls
    }


@router.post("/preview")
async def preview_import(
    request: ImportExecuteRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview an import before executing it.
    Validates mapped data and shows parsed values + errors for first N rows.
    """
    headers, rows = csv_parser.parse(request.csv_content)
    if not rows:
        raise HTTPException(400, "No data rows found in CSV")

    result = await import_pipeline.preview(
        db=db,
        tenant_id=current_user.tenant_id,
        entity_type=request.entity_type,
        rows=rows,
        mapping=request.mapping,
    )
    return result


@router.post("/execute", status_code=status.HTTP_201_CREATED)
async def execute_import(
    request: ImportExecuteRequest,
    current_user: User = Depends(require_finance),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a CSV import with the provided mapping.
    Creates/updates entities and returns import statistics.
    """
    headers, rows = csv_parser.parse(request.csv_content)
    if not rows:
        raise HTTPException(400, "No data rows found in CSV")

    # Optional preview check
    if not request.skip_preview:
        preview = await import_pipeline.preview(
            db=db,
            tenant_id=current_user.tenant_id,
            entity_type=request.entity_type,
            rows=rows,
            mapping=request.mapping,
        )
        if not preview["can_import"]:
            raise HTTPException(
                400,
                detail={
                    "message": "Import blocked: missing required field mappings",
                    "missing_required_fields": preview["missing_required_fields"],
                },
            )

    result = await import_pipeline.execute(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        entity_type=request.entity_type,
        rows=rows,
        mapping=request.mapping,
    )

    return result


@router.get("/history")
async def get_import_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List previous CSV import operations from audit logs."""
    query = select(AuditLog).where(
        AuditLog.tenant_id == current_user.tenant_id,
        AuditLog.action == "CSV_IMPORT",
    )
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(AuditLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    items = []
    for log in logs:
        items.append({
            "id": str(log.id),
            "entity_type": log.entity_type,
            "user_email": log.user_email,
            "result": log.after_state,
            "created_at": str(log.created_at),
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}
