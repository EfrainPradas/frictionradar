import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    Page,
    Browser,
    BrowserContext,
    Request,
    Response,
)
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PageCapture:
    capture_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_url: str = ""
    final_url: str = ""
    rendered_html: str = ""
    visible_text: str = ""
    visible_links: List[Dict[str, str]] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    screenshot_bytes: Optional[bytes] = None
    title: Optional[str] = None
    load_time_ms: int = 0
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None

    network_requests: List[Dict[str, Any]] = field(default_factory=list)
    network_responses: List[Dict[str, Any]] = field(default_factory=list)
    api_calls: List[Dict[str, Any]] = field(default_factory=list)
    embedded_json: List[Dict[str, Any]] = field(default_factory=list)
    page_state: Optional[Dict[str, Any]] = None
    preload_state: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        result = {
            "capture_id": self.capture_id,
            "source_url": self.source_url,
            "final_url": self.final_url,
            "visible_text": self.visible_text[:5000] if self.visible_text else "",
            "visible_links": self.visible_links[:30],
            "title": self.title,
            "load_time_ms": self.load_time_ms,
            "captured_at": self.captured_at.isoformat(),
            "error": self.error,
        }

        if self.network_requests:
            result["network_summary"] = {
                "total_requests": len(self.network_requests),
                "api_calls": len(self.api_calls),
                "sample_requests": [
                    r.get("url", "") for r in self.network_requests[:10]
                ],
            }

        if self.page_state:
            result["page_state"] = {"keys": list(self.page_state.keys())[:20]}

        return result


class BrowserCaptureService:
    DEFAULT_TIMEOUT_MS = 30000
    MAX_TEXT_LENGTH = 50000
    MAX_LINKS = 200
    MAX_NETWORK_LOG = 500
    MAX_RESPONSE_LOG = 200

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._request_log: List[Dict[str, Any]] = []
        self._response_log: List[Dict[str, Any]] = []
        self._pending_body_tasks: List[Any] = []  # asyncio tasks for response bodies

    async def initialize(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True, args=["--disable-blink-features=AutomationControlled"]
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

    async def cleanup(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None

    def _is_api_call(self, url: str) -> bool:
        api_patterns = [
            "/api/",
            "/graphql",
            "/v1/",
            "/v2/",
            "/search?",
            ".json",
            "/jobs/",
            "/positions/",
            "/search",
            "nginteractive",
            "workday",
            "lever",
            "greenhouse",
        ]
        url_lower = url.lower()
        return any(p in url_lower for p in api_patterns)

    async def capture_page(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
        wait_for_network_idle: bool = True,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        take_screenshot: bool = False,
        intercept_network: bool = True,
    ) -> PageCapture:
        capture = PageCapture(source_url=url)
        self._request_log = []
        self._response_log = []

        if not self._browser:
            await self.initialize()

        start_time = asyncio.get_event_loop().time()

        try:
            page = await self._context.new_page()

            if intercept_network:
                page.on("request", self._on_request)
                page.on("response", self._on_response)

            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            if wait_for_network_idle:
                try:
                    await page.wait_for_load_state("networkidle", timeout=timeout_ms)
                except Exception:
                    pass

            if wait_for_selector:
                try:
                    await page.wait_for_selector(
                        wait_for_selector, timeout=timeout_ms // 2
                    )
                except Exception:
                    pass

            await self._random_delay(500, 1500)

            capture.final_url = page.url
            capture.title = await page.title()

            html = await page.content()
            capture.rendered_html = html

            capture.visible_text = await self._extract_visible_text(page)
            capture.visible_links = await self._extract_visible_links(page)

            # Wait for all pending response body captures to finish
            await self._await_pending_bodies()

            capture.network_requests = self._request_log[: self.MAX_NETWORK_LOG]
            capture.network_responses = self._response_log[: self.MAX_RESPONSE_LOG]

            capture.api_calls = [
                r for r in self._request_log if self._is_api_call(r.get("url", ""))
            ][:50]

            capture.embedded_json = self._extract_embedded_json(html)
            capture.page_state = await self._extract_page_state(page)

            capture.preload_state = self._extract_preload_state(html)

            if take_screenshot:
                screenshot_bytes = await page.screenshot(full_page=True)
                capture.screenshot_bytes = screenshot_bytes

            capture.load_time_ms = int(
                (asyncio.get_event_loop().time() - start_time) * 1000
            )

            await page.close()

        except Exception as e:
            capture.error = str(e)
            logger.error(f"Browser capture failed for {url}: {e}")

        return capture

    def _on_request(self, request: Request):
        try:
            self._request_log.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception:
            pass

    def _on_response(self, response: Response):
        try:
            url = response.url
            status = response.status

            if status < 400 and self._is_api_call(url):
                resp_entry = {
                    "url": url,
                    "status": status,
                    "content_type": response.headers.get("content-type", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Schedule async body capture — it will be awaited before extraction
                try:
                    task = asyncio.create_task(self._capture_response_body(response, resp_entry))
                    self._pending_body_tasks.append(task)
                except RuntimeError:
                    # No event loop running — fall back to sync capture
                    pass

                self._response_log.append(resp_entry)
        except Exception:
            pass

    async def _capture_response_body(self, response: Response, resp_entry: dict):
        """Async task to capture response body without blocking the event loop.

        Bounded at 5s: Playwright's response.text() has no native timeout,
        so a slow/broken API response can hang the pipeline forever until
        the browser context itself times out. Dropping the body on timeout
        is preferable to stalling the whole worker.
        """
        try:
            body = await asyncio.wait_for(response.text(), timeout=5.0)
            if body and len(body) < 500000:
                resp_entry["body"] = body
        except Exception:
            pass

    async def _await_pending_bodies(self):
        """Wait for all pending response body captures to complete."""
        if self._pending_body_tasks:
            await asyncio.gather(*self._pending_body_tasks, return_exceptions=True)
            self._pending_body_tasks = []

    def _extract_embedded_json(self, html: str) -> List[Dict[str, Any]]:
        results = []

        patterns = [
            (r"window\.__NUK__\s*=\s*(\{.*?\});", "nuk"),
            (r"window\.__DATA__\s*=\s*(\{.*?\});", "data"),
            (r"window\.INITIAL_STATE__\s*=\s*(\{.*?\});", "initial_state"),
            (r"window\.STATE__\s*=\s*(\{.*?\});", "state"),
            (r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', "ld_json"),
            (r"window\.jobsData\s*=\s*(\{.*?\});", "jobs_data"),
            (r"window\.CAREERS_CONFIG\s*=\s*(\{.*?\});", "config"),
        ]

        for pattern, source in patterns:
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    data = json.loads(match)
                    results.append(
                        {
                            "source": source,
                            "keys": list(data.keys())[:20]
                            if isinstance(data, dict)
                            else "array",
                        }
                    )
                except json.JSONDecodeError:
                    continue

        return results

    async def _extract_page_state(self, page: Page) -> Optional[Dict[str, Any]]:
        try:
            state = await page.evaluate("""
                () => {
                    const state = {};
                    
                    for (const key of Object.keys(window)) {
                        if (key.startsWith('__') || key.startsWith('STATE') || 
                            key.includes('Data') || key.includes('Config') ||
                            key.includes('Jobs') || key.includes('Careers')) {
                            try {
                                const val = window[key];
                                if (typeof val === 'object' && val !== null) {
                                    state[key] = Object.keys(val).slice(0, 30);
                                }
                            } catch(e) {}
                        }
                    }
                    
                    return state;
                }
            """)
            return state if state else None
        except Exception as e:
            logger.warning(f"Failed to extract page state: {e}")
            return None

    def _extract_preload_state(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract __PRELOAD_STATE__ from HTML."""
        try:
            matches = re.findall(
                r"window\.__PRELOAD_STATE__\s*=\s*(\{.*?\});", html, re.DOTALL
            )
            if matches:
                return json.loads(matches[0])
        except Exception as e:
            logger.warning(f"Failed to extract preload state: {e}")
        return None

    async def _extract_visible_text(self, page: Page) -> str:
        try:
            text = await page.evaluate("""
                () => {
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    let text = '';
                    let node;
                    while (node = walker.nextNode()) {
                        const parent = node.parentElement;
                        if (parent && parent.tagName !== 'SCRIPT' && 
                            parent.tagName !== 'STYLE' && 
                            parent.tagName !== 'NOSCRIPT') {
                            const nodeText = node.textContent.trim();
                            if (nodeText.length > 0) {
                                text += nodeText + ' ';
                            }
                        }
                    }
                    return text;
                }
            """)
            return text[: self.MAX_TEXT_LENGTH].strip()
        except Exception as e:
            logger.warning(f"Failed to extract visible text: {e}")
            return ""

    async def _extract_visible_links(self, page: Page) -> List[Dict[str, str]]:
        try:
            links = await page.evaluate("""
                () => {
                    const anchors = document.querySelectorAll('a[href]');
                    const results = [];
                    anchors.forEach(a => {
                        const href = a.getAttribute('href');
                        const text = a.textContent.trim();
                        if (href && text.length > 0) {
                            results.push({
                                href: href,
                                text: text.substring(0, 200)
                            });
                        }
                    });
                    return results;
                }
            """)

            normalized_links = []
            for link in links[: self.MAX_LINKS]:
                href = link.get("href", "")
                text = link.get("text", "")

                if not href:
                    continue

                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    # Resolve relative URLs against the current page URL
                    if self._context and self._context.pages:
                        try:
                            page_url = url  # source_url passed to capture_page
                            from urllib.parse import urlparse, urljoin
                            parsed = urlparse(page_url)
                            base = f"{parsed.scheme}://{parsed.netloc}"
                            href = base + href
                        except Exception:
                            href = href

                normalized_links.append({"href": href, "text": text})

            return normalized_links
        except Exception as e:
            logger.warning(f"Failed to extract links: {e}")
            return []

    async def _random_delay(self, min_ms: int, max_ms: int):
        import random

        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

    async def find_careers_url(self, domain: str) -> Optional[str]:
        careers_paths = [
            "/careers",
            "/jobs",
            "/careers/jobs",
            "/job-openings",
            "/employment",
            "/join-us",
            "/work-with-us",
        ]

        base_url = f"https://{domain}"

        if not self._browser:
            await self.initialize()

        for path in careers_paths:
            url = base_url + path
            try:
                page = await self._context.new_page()
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=10000
                )

                if response and response.status == 200:
                    final_url = page.url
                    await page.close()

                    if "career" in final_url.lower() or "job" in final_url.lower():
                        return final_url

                await page.close()
            except Exception:
                continue

        return None


browser_capture_service = BrowserCaptureService()
