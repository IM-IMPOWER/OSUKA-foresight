from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from open_notebook.osuka.pipeline import run_osuka_pipeline
from open_notebook.osuka.competitors import _default_competitor_path

router = APIRouter()


class OsukaRunRequest(BaseModel):
    category: str = Field(..., description="Product category")
    market: Optional[str] = Field(None, description="Market/region (optional)")
    allow_external_brands: bool = Field(True, description="Allow non-listed brands")
    max_total: int = Field(10, description="Max products to discover")
    max_shopee_products: int = Field(10, description="Max Shopee products to fetch")
    prefer_pdfs: bool = Field(False, description="Prefer catalogue/manual PDFs")
    preferred_brands: Optional[List[str]] = Field(
        None,
        description="Preferred brand names to prioritize",
    )


class OsukaRunStartResponse(BaseModel):
    run_id: str


class OsukaRunStatusResponse(BaseModel):
    run_id: str
    status: str
    logs: List[str]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


RUN_STATE: Dict[str, Dict[str, Any]] = {}


async def _run_pipeline(run_id: str, request: OsukaRunRequest) -> None:
    try:
        def _log(message: str) -> None:
            RUN_STATE[run_id]["logs"].append(message)
            logger.info(message)

        result = await run_osuka_pipeline(
            category=request.category,
            market=request.market or "",
            allow_external_brands=request.allow_external_brands,
            max_total=request.max_total,
            max_shopee_products=request.max_shopee_products,
            prefer_pdfs=request.prefer_pdfs,
            competitor_path=_default_competitor_path(),
            preferred_brands=request.preferred_brands,
            progress_cb=_log,
        )
        RUN_STATE[run_id]["status"] = "completed"
        RUN_STATE[run_id]["result"] = result
    except Exception as exc:
        logger.error(f"OSUKA pipeline failed: {exc}")
        RUN_STATE[run_id]["status"] = "failed"
        RUN_STATE[run_id]["error"] = str(exc)


@router.post("/discovery/run", response_model=OsukaRunStartResponse)
async def run_osuka(request: OsukaRunRequest):
    """Run OSUKA discovery + Open Notebook table generation."""
    run_id = uuid4().hex
    RUN_STATE[run_id] = {
        "status": "running",
        "logs": ["DISCOVERY: queued"],
        "result": None,
        "error": None,
    }
    logger.info(f"OSUKA run queued: {run_id}")
    import asyncio
    asyncio.create_task(_run_pipeline(run_id, request))
    return OsukaRunStartResponse(run_id=run_id)


@router.get("/discovery/run/{run_id}", response_model=OsukaRunStatusResponse)
async def get_osuka_status(run_id: str):
    if run_id not in RUN_STATE:
        raise HTTPException(status_code=404, detail="Run not found")
    state = RUN_STATE[run_id]
    return OsukaRunStatusResponse(
        run_id=run_id,
        status=state.get("status", "unknown"),
        logs=state.get("logs", []),
        result=state.get("result"),
        error=state.get("error"),
    )
