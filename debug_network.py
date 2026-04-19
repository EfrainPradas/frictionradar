import asyncio
import json
import re
import sys

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from app.services.browser_capture_service import BrowserCaptureService


async def main():
    service = BrowserCaptureService()
    await service.initialize()

    capture = await service.capture_page(
        "https://careers.nike.com", timeout_ms=30000, intercept_network=True
    )

    html = capture.rendered_html

    print("=== EXTRACTING __PRELOAD_STATE__ ===")
    preload_matches = re.findall(
        r"window\.__PRELOAD_STATE__\s*=\s*(\{.*?\});", html, re.DOTALL
    )

    for match in preload_matches:
        try:
            data = json.loads(match)

            if "jobSearch" in data:
                job_search = data["jobSearch"]
                print(f"totalJob: {job_search.get('totalJob')}")
                print(f"params: {job_search.get('params')}")
                print(f"jobs count: {len(job_search.get('jobs', []))}")

                if "facets" in job_search:
                    facets = job_search["facets"]
                    print(
                        f"facets keys: {list(facets.keys()) if isinstance(facets, dict) else type(facets)}"
                    )

                    if isinstance(facets, dict):
                        for facet_name, facet_data in facets.items():
                            if isinstance(facet_data, dict) and "buckets" in facet_data:
                                buckets = facet_data["buckets"][:5]
                                print(
                                    f"  {facet_name}: {[(b.get('name'), b.get('count')) for b in buckets]}"
                                )

            if "company" in data:
                print(f"company: {list(data['company'].keys())}")

        except Exception as e:
            print(f"Error: {e}")

    print("\n=== JOB SAMPLE ===")
    for match in preload_matches:
        try:
            data = json.loads(match)
            if "jobSearch" in data:
                jobs = data["jobSearch"].get("jobs", [])
                for job in jobs[:3]:
                    print(f"  Title: {job.get('title')}")
                    print(f"  Location: {job.get('location')}")
                    print(f"  Category: {job.get('category')}")
                    print(f"  URL: {job.get('url')}")
                    print()
        except:
            pass

    await service.cleanup()


asyncio.run(main())
