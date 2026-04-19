import asyncio
import sys
import re

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from app.services.browser_capture_service import BrowserCaptureService
from bs4 import BeautifulSoup
import json


async def main():
    service = BrowserCaptureService()
    await service.initialize()

    capture = await service.capture_page("https://careers.nike.com", timeout_ms=30000)

    html = capture.rendered_html

    print("=== Looking for window.__data or JSON data ===")

    data_patterns = [
        r"window\.__NUK__\s*=\s*(\{.*?\});",
        r"window\.dataLayer\s*=\s*(\[.*?\]);",
        r'"total":\s*(\d+)',
        r'"count":\s*(\d+)',
        r'"totalCount":\s*(\d+)',
    ]

    for p in data_patterns:
        matches = re.findall(p, html, re.DOTALL | re.IGNORECASE)
        if matches:
            print(f"Pattern '{p[:30]}...': {matches[:2]}")

    print("\n=== Looking for filter counts that sum to total ===")
    soup = BeautifulSoup(html, "html.parser")

    full_time_count = 0
    part_time_count = 0

    for elem in soup.find_all(string=re.compile(r"Full Time|Part Time")):
        parent = elem.parent
        if parent:
            text = parent.get_text()
            ft_match = re.search(r"Full Time(\d+)", text)
            pt_match = re.search(r"Part Time(\d+)", text)
            if ft_match:
                full_time_count = int(ft_match.group(1))
            if pt_match:
                part_time_count = int(pt_match.group(1))

    print(f"Full Time: {full_time_count}, Part Time: {part_time_count}")
    print(f"Total: {full_time_count + part_time_count}")

    print("\n=== Looking at script tags for data ===")
    for script in soup.find_all("script"):
        src = script.get("src", "")
        if "init" in src or "data" in src:
            print(f"Script src: {src[:80]}")

    print("\n=== Try evaluate JS to get count ===")

    await service.cleanup()


asyncio.run(main())
