from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx


@dataclass(slots=True)
class FetchResult:
    url: str
    status_code: int
    content_type: str
    text: str
    headers: dict[str, str]


class FetchError(RuntimeError):
    pass


class PoliteFetcher:
    """Small async HTTP client with retries, size limit, per-host delay and robots check."""

    def __init__(self, user_agent: str, timeout: float = 20, delay: float = 0.8,
                 max_bytes: int = 5_000_000, respect_robots: bool = True):
        self.user_agent = user_agent
        self.timeout = timeout
        self.delay = max(0.0, delay)
        self.max_bytes = max_bytes
        self.respect_robots = respect_robots
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/atom+xml,application/json;q=0.9,*/*;q=0.7"},
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
        )
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}
        self.warnings: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    async def aclose(self):
        await self._client.aclose()

    @staticmethod
    def _origin(url: str) -> str:
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.netloc, "", "", ""))

    async def _throttle(self, url: str):
        origin = self._origin(url)
        loop = asyncio.get_running_loop()
        now = loop.time()
        wait_for = self.delay - (now - self._last_request.get(origin, 0.0))
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        self._last_request[origin] = loop.time()

    async def _get_robots(self, url: str) -> RobotFileParser | None:
        origin = self._origin(url)
        if origin in self._robots:
            return self._robots[origin]
        robots_url = origin + "/robots.txt"
        parser = RobotFileParser()
        try:
            await self._throttle(robots_url)
            response = await self._client.get(robots_url)
            if response.status_code == 200 and len(response.content) <= 512_000:
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
                self._robots[origin] = parser
            elif response.status_code in (404, 410):
                self._robots[origin] = None
            else:
                self.warnings.append(f"Không xác định được robots.txt của {origin} (HTTP {response.status_code}); tiếp tục với cảnh báo.")
                self._robots[origin] = None
        except httpx.HTTPError as exc:
            self.warnings.append(f"Không đọc được robots.txt của {origin}: {exc}; cần tự kiểm tra chính sách nguồn.")
            self._robots[origin] = None
        return self._robots[origin]

    async def get(self, url: str, *, check_robots: bool = True, allow_http_errors: bool = False) -> FetchResult:
        if self.respect_robots and check_robots:
            robots = await self._get_robots(url)
            if robots and not robots.can_fetch(self.user_agent, url):
                raise FetchError(f"Bị robots.txt chặn: {url}")
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                await self._throttle(url)
                async with self._client.stream("GET", url) as response:
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise FetchError(f"Phản hồi vượt giới hạn {self.max_bytes} byte: {url}")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    if not allow_http_errors and response.status_code >= 400:
                        if response.status_code in (408, 425, 429) or response.status_code >= 500:
                            response.raise_for_status()
                        raise FetchError(f"HTTP {response.status_code}: {url}")
                    encoding = response.encoding or "utf-8"
                    text = body.decode(encoding, errors="replace")
                    return FetchResult(
                        url=str(response.url), status_code=response.status_code,
                        content_type=response.headers.get("content-type", "").lower(),
                        text=text, headers={k.lower(): v for k, v in response.headers.items()},
                    )
            except FetchError:
                raise
            except (httpx.HTTPError, UnicodeError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.7 * (attempt + 1))
        raise FetchError(f"Không tải được {url}: {last_error}")
