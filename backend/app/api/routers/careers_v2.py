from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
import traceback

from app.db.session import get_db
from app.services.browser_capture_service import browser_capture_service, PageCapture
from app.services.hybrid_careers_extractor import hybrid_careers_extractor
from app.schemas.careers_page import CareersPageExtraction, CareersPageSignals
from app.models.page_capture import PageCapture as PageCaptureModel
from app.models.company import Company
from app.models.company_job_role import CompanyJobRole
from app.models.company_signal import CompanySignal
from app.services.role_ingest import persist_job_role

router = APIRouter()


class CareersPageExtractRequest(BaseModel):
    domain: str
    careers_url: Optional[str] = None


@router.post("/extract-careers-page")
async def extract_careers_page(
    request: CareersPageExtractRequest, db: Session = Depends(get_db)
):
    """Extract structured careers page data using hybrid extraction strategy."""

    careers_url = request.careers_url

    if not careers_url:
        careers_url = f"https://{request.domain}/careers"
        if not careers_url.endswith("/careers") and not careers_url.endswith("/jobs"):
            careers_url = f"https://careers.{request.domain}"

    try:
        capture = await browser_capture_service.capture_page(
            url=careers_url,
            wait_for_selector=None,
            wait_for_network_idle=True,
            timeout_ms=30000,
            take_screenshot=False,
            intercept_network=True,
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Failed to capture page: {str(e)}",
                "trace": traceback.format_exc(),
            },
        )

    if capture.error:
        return JSONResponse(
            status_code=502,
            content={"detail": f"Browser capture failed: {capture.error}"},
        )

    try:
        extraction = await hybrid_careers_extractor.extract(
            rendered_html=capture.rendered_html,
            visible_text=capture.visible_text,
            visible_links=capture.visible_links,
            network_requests=capture.network_requests,
            network_responses=capture.network_responses,
            embedded_json=capture.embedded_json,
            page_state=capture.page_state,
            source_url=capture.final_url or careers_url,
            preload_state=capture.preload_state,
        )

        extraction_schema = CareersPageExtraction(
            page_type=extraction.page_type,
            open_positions_count=extraction.open_positions_count,
            visible_hiring_areas=extraction.visible_hiring_areas or [],
            visible_role_cards=extraction.visible_role_cards or [],
            visible_locations=extraction.visible_locations or [],
            evidence_quality=extraction.evidence_quality,
            what_is_clearly_visible=extraction.what_is_clearly_visible or [],
            what_is_still_unclear=extraction.what_is_still_unclear or [],
            source_url=capture.final_url or careers_url,
        )

        signals = CareersPageSignals()
        if extraction.open_positions_count:
            signals.open_positions_count_detected = True
            if extraction.open_positions_count >= 100:
                signals.high_open_positions_count_detected = True
        if extraction.visible_role_cards:
            signals.job_cards_visible_detected = True
        if extraction.visible_hiring_areas:
            signals.visible_hiring_area_detected = True

        result = {
            "capture": capture.to_dict(),
            "extraction": extraction_schema.model_dump(),
            "signals": signals.model_dump(),
            "source_of_truth": extraction.source_of_truth,
            "source_details": extraction.source_details,
        }

        try:
            company = db.query(Company).filter(Company.domain == request.domain).first()
            company_id = company.id if company else None

            page_capture = PageCaptureModel(
                company_id=company_id,
                source_url=careers_url,
                final_url=capture.final_url or careers_url,
                title=capture.title,
                rendered_html=capture.rendered_html[:10000]
                if capture.rendered_html
                else None,
                visible_text=capture.visible_text[:5000]
                if capture.visible_text
                else None,
                visible_links_json=str(capture.visible_links[:20]),
                load_time_ms=capture.load_time_ms,
                page_type=extraction.page_type,
                page_type_confidence=extraction.evidence_quality,
                extraction_status="completed",
                extraction_result_json=str(extraction_schema.model_dump()),
            )
            db.add(page_capture)

            job_roles_saved = 0
            if company_id and extraction.visible_role_cards:
                for card in extraction.visible_role_cards[:20]:
                    if persist_job_role(
                        db,
                        company_id=company_id,
                        raw_title=card.title,
                        source_url=card.job_url or careers_url,
                        role_location=card.location,
                    ) is not None:
                        job_roles_saved += 1

            if company_id:
                for signal_data in signals.to_signal_list():
                    signal = CompanySignal(
                        company_id=company_id,
                        source_type="browser_capture_v2",
                        source_url=capture.final_url or careers_url,
                        signal_type=signal_data["type"],
                        signal_text=signal_data["text"],
                        confidence=0.85,
                    )
                    db.add(signal)

                if extraction.open_positions_count:
                    signal_type = (
                        "high_open_positions_count_detected"
                        if extraction.open_positions_count >= 100
                        else "open_positions_count_detected"
                    )
                    count_signal = CompanySignal(
                        company_id=company_id,
                        source_type="browser_capture_v2",
                        source_url=capture.final_url or careers_url,
                        signal_type=signal_type,
                        signal_text=f"Open positions: {extraction.open_positions_count}",
                        numeric_value=extraction.open_positions_count,
                        confidence=0.9,
                    )
                    db.add(count_signal)

            db.commit()
            result["job_roles_saved"] = job_roles_saved
        except Exception as db_error:
            result["db_warning"] = f"DB save failed: {str(db_error)}"

        return result

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Extraction failed: {str(e)}",
                "trace": traceback.format_exc(),
            },
        )


@router.get("/captures", response_model=List[dict])
def get_page_captures(
    domain: Optional[str] = None, limit: int = 20, db: Session = Depends(get_db)
):
    """Get recent page captures."""
    query = db.query(PageCaptureModel)

    if domain:
        company = db.query(Company).filter(Company.domain == domain).first()
        if company:
            query = query.filter(PageCaptureModel.company_id == company.id)

    captures = query.order_by(PageCaptureModel.captured_at.desc()).limit(limit).all()

    return [
        {
            "id": str(c.id),
            "source_url": c.source_url,
            "final_url": c.final_url,
            "page_type": c.page_type,
            "evidence_quality": c.page_type_confidence,
            "captured_at": c.captured_at.isoformat() if c.captured_at else None,
        }
        for c in captures
    ]
