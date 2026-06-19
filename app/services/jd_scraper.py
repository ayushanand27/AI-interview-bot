"""Fetch and extract job description text from public job posting URLs."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.exceptions import BadRequestException

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

FETCH_TIMEOUT_SECONDS = 20.0
MIN_JD_CHARS = 80


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _extract_from_soup(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = _normalize_whitespace(node.get_text(separator="\n", strip=True))
            if len(text) >= MIN_JD_CHARS:
                return text
    return ""


def _generic_extract(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    for selector in ("main", "article", '[role="main"]'):
        node = soup.select_one(selector)
        if node:
            parts = [
                el.get_text(separator=" ", strip=True)
                for el in node.find_all(["p", "li"])
            ]
            text = _normalize_whitespace("\n".join(parts))
            if len(text) >= MIN_JD_CHARS:
                return text

    paragraphs = [
        p.get_text(separator=" ", strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 40
    ]
    if paragraphs:
        return _normalize_whitespace("\n".join(paragraphs))

    body = soup.body
    if body:
        return _normalize_whitespace(body.get_text(separator="\n", strip=True))
    return ""


def _detect_source(url: str, host: str) -> str:
    host = host.lower()
    if "naukri.com" in host:
        return "naukri"
    if "indeed." in host:
        return "indeed"
    if "linkedin.com" in host:
        return "linkedin"
    return "generic"


def _selectors_for_source(source: str) -> list[str]:
    if source == "naukri":
        return [
            ".styles_JDC__dang-inner-html__h0K4y",
            '[class*="jd-desc-container"]',
            ".jd-desc",
            ".job-desc",
            '[class*="jd-desc"]',
            '[class*="job-desc"]',
        ]
    if source == "indeed":
        return [
            "#jobDescriptionText",
            ".jobsearch-jobDescriptionText",
            '[id*="jobDescription"]',
        ]
    if source == "linkedin":
        return [
            ".description__text",
            ".show-more-less-html__markup",
            '[class*="description__text"]',
            ".jobs-description__content",
        ]
    return []


async def fetch_jd_from_url(url: str) -> tuple[str, str]:
    """Return (jd_text, source). Raises BadRequestException on failure."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise BadRequestException("Please provide a valid http or https job URL.")

    source = _detect_source(url, parsed.netloc)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise BadRequestException(
            "Could not extract JD from this URL — request timed out. Please paste manually."
        ) from exc
    except httpx.HTTPError as exc:
        raise BadRequestException(
            "Could not extract JD from this URL — please paste manually."
        ) from exc

    content_type = (response.headers.get("content-type") or "").lower()
    if "html" not in content_type and "text" not in content_type:
        raise BadRequestException(
            "Could not extract JD from this URL — unsupported response type."
        )

    soup = BeautifulSoup(response.text, "lxml")
    jd_text = _extract_from_soup(soup, _selectors_for_source(source))
    if not jd_text:
        jd_text = _generic_extract(soup)

    jd_text = _normalize_whitespace(jd_text)
    if len(jd_text) < MIN_JD_CHARS:
        raise BadRequestException(
            "Could not extract JD from this URL — please paste manually."
        )

    return jd_text[:50000], source
