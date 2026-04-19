import asyncio
import json
import sys

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from app.services.browser_capture_service import BrowserCaptureService


async def main():
    service = BrowserCaptureService()
    await service.initialize()

    capture = await service.capture_page("https://careers.nike.com", timeout_ms=30000)

    html = capture.rendered_html

    import re

    preload_matches = re.findall(
        r"window\.__PRELOAD_STATE__\s*=\s*(\{.*?\});", html, re.DOTALL
    )

    for match in preload_matches:
        data = json.loads(match)
        if "jobSearch" in data:
            print("=== FACETS ===")
            facets = data["jobSearch"].get("facets", [])
            print(f"Type: {type(facets)}")
            if isinstance(facets, list):
                for facet in facets[:3]:
                    print(f"Facet: {facet}")

    await service.cleanup()


asyncio.run(main())
