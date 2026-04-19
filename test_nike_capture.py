import asyncio
import sys

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from app.services.browser_capture_service import BrowserCaptureService
from app.services.careers_page_ai_extractor import careers_page_ai_extractor
import json


async def main():
    service = BrowserCaptureService()
    await service.initialize()

    try:
        capture = await service.capture_page(
            "https://careers.nike.com", timeout_ms=30000
        )

        result = {
            "capture_error": capture.error,
            "final_url": capture.final_url,
            "title": capture.title[:100] if capture.title else None,
            "text_length": len(capture.visible_text) if capture.visible_text else 0,
            "links_count": len(capture.visible_links) if capture.visible_links else 0,
        }

        if capture.rendered_html and not capture.error:
            extraction = await careers_page_ai_extractor.extract(
                rendered_html=capture.rendered_html,
                visible_text=capture.visible_text,
                visible_links=capture.visible_links,
                source_url="https://careers.nike.com",
            )
            result["extraction"] = {
                "page_type": extraction.page_type,
                "open_positions_count": extraction.open_positions_count,
                "job_cards_count": len(extraction.visible_role_cards),
                "hiring_areas": extraction.visible_hiring_areas,
                "evidence_quality": extraction.evidence_quality,
            }

        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e), "trace": str(sys.exc_info())}))
    finally:
        await service.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
