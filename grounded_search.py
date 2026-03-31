import html
import io
import re
from urllib.parse import quote_plus, urlparse

import aiohttp


SEARCH_USER_AGENT = "Mozilla/5.0 (compatible; ScaraWandererBots/1.0; +https://github.com/Kittybri)"
URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


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


def extract_urls(text: str, max_urls: int = 2) -> list[str]:
    if not text:
        return []
    urls: list[str] = []
    for match in URL_RE.findall(text):
        cleaned = match.rstrip(").,!?:;\"'")
        if cleaned not in urls:
            urls.append(cleaned)
        if len(urls) >= max_urls:
            break
    return urls


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _collapse_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


async def fetch_url_preview(url: str, max_chars: int = 900) -> dict:
    target = (url or "").strip()
    if not target:
        return {}

    headers = {
        "User-Agent": SEARCH_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    timeout = aiohttp.ClientTimeout(total=12)

    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(target, allow_redirects=True) as resp:
                if resp.status != 200:
                    return {}
                final_url = str(resp.url)
                content_type = (resp.headers.get("Content-Type") or "").lower()
                host = urlparse(final_url).netloc or urlparse(target).netloc or "source"

                if "pdf" in content_type or final_url.lower().endswith(".pdf"):
                    data = await resp.read()
                    text = ""
                    try:
                        import pdfplumber

                        with pdfplumber.open(io.BytesIO(data)) as pdf:
                            text = "\n".join((page.extract_text() or "")[:1200] for page in pdf.pages[:3])
                    except Exception:
                        try:
                            import PyPDF2

                            reader = PyPDF2.PdfReader(io.BytesIO(data))
                            text = "\n".join((page.extract_text() or "")[:1200] for page in reader.pages[:3])
                        except Exception:
                            text = ""
                    text = _collapse_space(text)[:max_chars]
                    return {
                        "url": final_url,
                        "kind": "pdf",
                        "title": f"PDF from {host}",
                        "snippet": text,
                    }

                raw = await resp.text(errors="ignore")
    except Exception:
        return {}

    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
    og_title_match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', raw, re.IGNORECASE | re.DOTALL)
    desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', raw, re.IGNORECASE | re.DOTALL)
    og_desc_match = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', raw, re.IGNORECASE | re.DOTALL)
    paragraph_match = re.search(r"<p[^>]*>(.*?)</p>", raw, re.IGNORECASE | re.DOTALL)

    title = html.unescape(_collapse_space(_strip_tags((og_title_match or title_match or [None, ""])[1])))
    snippet = html.unescape(
        _collapse_space(
            _strip_tags(
                (og_desc_match or desc_match or paragraph_match or [None, ""])[1]
            )
        )
    )
    if not title:
        host = urlparse(target).netloc or "source"
        title = f"Page from {host}"
    return {
        "url": final_url,
        "kind": "html",
        "title": title[:180],
        "snippet": snippet[:max_chars],
    }


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


def format_url_preview_context(preview: dict) -> str:
    if not preview:
        return ""
    title = (preview.get("title") or "Linked page").strip()
    url = (preview.get("url") or "").strip()
    kind = (preview.get("kind") or "page").strip()
    snippet = (preview.get("snippet") or "").strip()
    return f"URL_PREVIEW:{kind}|{title}|{url}|{snippet[:700]}"


def format_search_sources(results: list[dict], max_results: int = 3) -> str:
    if not results:
        return ""
    lines = ["Sources:"]
    for idx, item in enumerate(results[:max_results], start=1):
        lines.append(f"[{idx}] {item.get('title','Source')} - {item.get('url','')}")
    return "\n".join(lines)
