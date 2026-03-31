"""
Sales IQ - Demo Data API Endpoints
Generate, clear, and inspect demo datasets for the platform.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, RoleChecker
from app.models.core import User, UserRole
from app.services.demo_data import demo_data_manager, DATASET_SIZES, ERP_PROFILES

router = APIRouter()

require_admin = RoleChecker(UserRole.TENANT_ADMIN)


# =============================================
# Schemas
# =============================================

class GenerateRequest(BaseModel):
    size: str = Field(
        "medium",
        description="Dataset size: small (~10 customers), medium (~20), large (~30)",
        pattern="^(small|medium|large)$",
    )
    erp_profile: str = Field(
        "d365_fo",
        description="ERP source profile: d365_fo, sap_b1, generic",
        pattern="^(d365_fo|sap_b1|generic)$",
    )


class ClearRequest(BaseModel):
    confirm: bool = Field(
        ...,
        description="Must be True to confirm deletion of demo data",
    )


# =============================================
# Endpoints
# =============================================

@router.get("/profiles")
async def list_profiles(
    current_user: User = Depends(get_current_user),
):
    """List available ERP profiles and dataset sizes."""
    return {
        "erp_profiles": {
            key: {"display_name": val["display_name"], "source_system": val["source_system"]}
            for key, val in ERP_PROFILES.items()
        },
        "dataset_sizes": {
            key: {
                "customers": val["customers"],
                "invoices_per_customer": f"{val['invoices_per_customer'][0]}-{val['invoices_per_customer'][1]}",
                "payment_probability": f"{val['payment_probability']:.0%}",
            }
            for key, val in DATASET_SIZES.items()
        },
    }


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_demo_data(
    request: GenerateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a realistic demo dataset for the current tenant.
    Includes customers, invoices, payments, disputes, and collection activities.
    All records are tagged source_system='DEMO' for easy cleanup.
    """
    try:
        stats = await demo_data_manager.generate(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            size=request.size,
            erp_profile=request.erp_profile,
        )
        return {
            "message": f"Demo data generated successfully ({request.size} dataset, {request.erp_profile} profile)",
            **stats,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/clear", status_code=status.HTTP_200_OK)
@router.post("/clear", status_code=status.HTTP_200_OK)
async def clear_demo_data(
    request: ClearRequest = ClearRequest(confirm=True),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove all demo-tagged records (source_system='DEMO') from the current tenant.
    Does NOT affect real/production data.
    Accepts both DELETE and POST for maximum compatibility.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to proceed with demo data deletion",
        )

    try:
        counts = await demo_data_manager.clear(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear demo data: {str(e)}",
        )
    return {
        "message": "Demo data cleared successfully",
        "deleted": counts,
    }


@router.get("/stats")
async def get_demo_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current data statistics showing demo vs. real record counts.
    """
    stats = await demo_data_manager.get_stats(
        db=db,
        tenant_id=current_user.tenant_id,
    )
    return stats
