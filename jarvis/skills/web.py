"""Web and YouTube skills (browser navigation, read-back, video lookup)."""
from __future__ import annotations

import re
import webbrowser
from html.parser import HTMLParser
from typing import List
from urllib.parse import quote_plus, urlparse

import requests

from . import register

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_VIDEO_ID = re.compile(r"watch\?v=([\w-]{11})")
_MAX_READ = 6000


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.chunks: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self.chunks.append(data.strip())


def _open(url: str) -> str:
    webbrowser.open(url)
    return f"Opened {urlparse(url).netloc} in the default browser."


def _html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": _UA,
                                   "Accept-Language": "en"},
                     timeout=15)
    r.raise_for_status()
    return r.text


def _first_video_id(html: str) -> str:
    """First videoId in the ytInitialData blob is the top result."""
    m = _VIDEO_ID.search(html)
    return m.group(1) if m else ""


@register("web_open", "Open a website (http/https) in the default browser.",
          "{url}")
def web_open(url: str) -> str:
    url = url.strip()
    if not urlparse(url).scheme:
        url = "https://" + url
    return _open(url)


@register("web_search", "Search the web and show results in the browser.",
          "{query}")
def web_search(query: str) -> str:
    return _open("https://www.google.com/search?q=" + quote_plus(query))


@register("web_read", "Fetch a web page's text and return it for you to "
          "summarise or quote (read-only GET).", "{url}", returns_data=True)
def web_read(url: str) -> str:
    try:
        html = _html(url)
    except Exception as exc:
        return f"ERROR: could not fetch the page ({exc})."
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = re.sub(r"\s+", " ", " ".join(parser.chunks))
    if len(text) > _MAX_READ:
        text = text[:_MAX_READ] + " …[truncated]"
    return text or "ERROR: the page had no readable text."


@register("youtube_search", "Show YouTube search results on screen.", "{query}")
def youtube_search(query: str) -> str:
    return _open("https://www.youtube.com/results?search_query=" + quote_plus(query))


@register("youtube_channel", "Open a creator's YouTube channel page.",
          "{name}")
def youtube_channel(name: str) -> str:
    handle = name.strip().lstrip("@").replace(" ", "")
    return _open(f"https://www.youtube.com/@{quote_plus(handle)}/videos")


@register("youtube_play", "Play the best-match video for a query or creator on "
          "YouTube right now (resolves the top result and opens its watch "
          "page; falls back to the results page).", "{query}")
def youtube_play(query: str) -> str:
    search_url = ("https://www.youtube.com/results?search_query="
                  + quote_plus(query))
    try:
        vid = _first_video_id(_html(search_url))
    except Exception:
        vid = ""
    if vid:
        return _open(f"https://www.youtube.com/watch?v={vid}")
    return _open(search_url)


@register("youtube_latest", "Play the newest video from a YouTube creator.",
          "{channel}")
def youtube_latest(channel: str) -> str:
    handle = channel.strip().lstrip("@").replace(" ", "")
    page = f"https://www.youtube.com/@{quote_plus(handle)}/videos"
    try:
        vid = _first_video_id(_html(page))
    except Exception:
        vid = ""
    if vid:
        return _open(f"https://www.youtube.com/watch?v={vid}")
    return _open(page)
