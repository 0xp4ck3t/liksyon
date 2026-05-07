import asyncio
import json
import random
import re
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page

COOKIES_PATH = Path("data/cookies.json")

API_FIELDS = (
    "?page_size=200"
    "&fields[lecture]=title,object_index,is_published,sort_order,created,asset,is_free"
    "&fields[chapter]=title,object_index,is_published,sort_order"
    "&fields[asset]=title,filename,asset_type,status,time_estimation,is_external,captions"
    "&caching_intent=True"
)


class UdemyScraper:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self.context: BrowserContext = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=False)
        self.context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        await self._load_cookies()
        return self

    async def __aexit__(self, *args):
        await self._save_cookies()
        await self._browser.close()
        await self._playwright.stop()

    async def _load_cookies(self):
        if COOKIES_PATH.exists():
            cookies = json.loads(COOKIES_PATH.read_text())
            await self.context.add_cookies(cookies)

    async def _save_cookies(self):
        cookies = await self.context.cookies()
        COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_PATH.write_text(json.dumps(cookies, indent=2))

    async def _is_logged_in(self, page: Page) -> bool:
        await page.goto("https://www.udemy.com/", wait_until="domcontentloaded")
        return await page.locator('[data-purpose="user-dropdown"]').count() > 0

    async def login(self, page: Page):
        print("\nOpening Udemy login page — please log in manually in the browser window.")
        print("The script will continue automatically once you're logged in.\n")
        await page.goto("https://www.udemy.com/join/login-popup/", wait_until="domcontentloaded")
        await page.wait_for_url("https://www.udemy.com/**", timeout=180_000)
        print("Login detected. Saving session cookies...")

    async def _fetch_json(self, page: Page, url: str) -> dict:
        await page.goto(url, wait_until="networkidle")
        raw = await page.evaluate("() => document.body.innerText")
        return json.loads(raw)

    async def get_enrolled_course_ids(self, page: Page) -> set[str]:
        data = await self._fetch_json(
            page,
            "https://www.udemy.com/api-2.0/users/me/subscribed-courses/"
            "?page_size=100&fields[course]=id",
        )
        return {str(c["id"]) for c in data.get("results", [])}

    async def get_course_id(self, page: Page, course_url: str) -> str:
        await page.goto(course_url, wait_until="domcontentloaded")
        course_id = await page.evaluate(
            "() => document.querySelector('body[data-clp-course-id]')"
            "?.getAttribute('data-clp-course-id')"
        )
        if not course_id:
            raise ValueError(f"Could not extract course ID from {course_url}")
        return course_id

    async def get_course_structure(self, page: Page, course_id: str) -> list[dict]:
        url = f"https://www.udemy.com/api-2.0/courses/{course_id}/subscriber-curriculum-items/{API_FIELDS}"
        data = await self._fetch_json(page, url)
        return data.get("results", [])

    async def _fetch_vtt(self, page: Page, vtt_url: str) -> str:
        return await page.evaluate(
            """(url) => fetch(url).then(r => r.text())""",
            vtt_url,
        )

    def _parse_vtt(self, vtt: str) -> str:
        lines = []
        for line in vtt.splitlines():
            line = line.strip()
            if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                continue
            # strip inline VTT tags like <00:00:01.000><c>text</c>
            line = re.sub(r"<[^>]+>", "", line)
            lines.append(line)
        # deduplicate consecutive duplicate lines (Udemy sometimes repeats lines)
        deduped = [lines[i] for i in range(len(lines)) if i == 0 or lines[i] != lines[i - 1]]
        return " ".join(deduped)

    async def scrape_course(self, course_url: str) -> list[dict]:
        page = await self.context.new_page()

        if not await self._is_logged_in(page):
            await self.login(page)
            await self._save_cookies()

        print("Checking course ownership...")
        enrolled_ids = await self.get_enrolled_course_ids(page)

        course_id = await self.get_course_id(page, course_url)

        if course_id not in enrolled_ids:
            await page.close()
            raise PermissionError(
                f"Course {course_id} not found in your enrolled courses. "
                "Liksyon only processes courses you own."
            )

        print(f"Course ID: {course_id} — ownership confirmed.")
        print("Fetching course structure...")

        results = await self.get_course_structure(page, course_id)

        lectures = []
        current_chapter = "Uncategorized"

        for item in results:
            cls = item.get("_class")
            if cls == "chapter":
                current_chapter = item["title"]
            elif cls == "lecture":
                asset = item.get("asset") or {}
                if not str(asset.get("asset_type", "")).lower().startswith("video"):
                    continue

                captions = asset.get("captions") or []
                en = next((c for c in captions if str(c.get("locale_id", "")).startswith("en")), None)
                caption = en or (captions[0] if captions else None)

                lectures.append({
                    "id": str(item["id"]),
                    "title": item["title"],
                    "chapter": current_chapter,
                    "course_id": course_id,
                    "caption_url": caption["url"] if caption else None,
                    "locale": caption.get("locale_id") if caption else None,
                })

        print(f"Found {len(lectures)} video lectures across course.")

        transcripts = []
        for i, lecture in enumerate(lectures):
            print(f"  [{i + 1}/{len(lectures)}] {lecture['chapter']} — {lecture['title']}")

            if lecture["caption_url"]:
                vtt = await self._fetch_vtt(page, lecture["caption_url"])
                transcript_text = self._parse_vtt(vtt)
            else:
                print("    (no captions available — skipping)")
                transcript_text = None

            transcripts.append({**lecture, "transcript": transcript_text})

            if i < len(lectures) - 1:
                await asyncio.sleep(random.uniform(3, 8))

        await page.close()
        return transcripts
