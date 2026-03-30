import html
import re
from urllib.parse import quote_plus

import aiohttp


SEARCH_USER_AGENT = "Mozilla/5.0 (compatible; ScaraWandererBots/1.0; +https://github.com/Kittybri)"


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    text = (query or "").strip()
    if not text:
        return []

    headers = {
        "User-Agent": SEARCH_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    url = f"https://duckduckgo.com/html/?q={quote_plus(text)}"
    timeout = aiohttp.ClientTimeout(total=12)

    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                page = await resp.text()
    except Exception:
        return []

    results: list[dict] = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>(?P<body>.*?)(?=<a[^>]+class="result__a"|$)',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)
    tag_pattern = re.compile(r"<[^>]+>")

    for match in pattern.finditer(page):
        raw_url = html.unescape(match.group("url") or "")
        if not raw_url.startswith("http"):
            continue
        title = tag_pattern.sub("", html.unescape(match.group("title") or "")).strip()
        body = match.group("body") or ""
        snippet_match = snippet_pattern.search(body)
        snippet_raw = snippet_match.group(1) or snippet_match.group(2) if snippet_match else ""
        snippet = tag_pattern.sub("", html.unescape(snippet_raw or "")).strip()
        if not title:
            continue
        results.append({"title": title[:160], "url": raw_url[:500], "snippet": snippet[:260]})
        if len(results) >= max_results:
            break
    return results


def format_search_context(results: list[dict]) -> str:
    if not results:
        return ""
    lines = []
    for idx, item in enumerate(results, start=1):
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        lines.append(f"[{idx}] {title} | {url} | {snippet}")
    return "\n".join(lines)


def format_search_sources(results: list[dict], max_results: int = 3) -> str:
    if not results:
        return ""
    lines = ["Sources:"]
    for idx, item in enumerate(results[:max_results], start=1):
        lines.append(f"[{idx}] {item.get('title','Source')} - {item.get('url','')}")
    return "\n".join(lines)
