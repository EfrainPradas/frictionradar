import asyncio
import sys

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from app.services.collection_orchestrator import find_careers_url


async def main():
    url = await find_careers_url("nike.com")
    print(f"Found careers URL: {url}")


asyncio.run(main())
