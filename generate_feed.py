from __future__ import annotations

import datetime as dt
import html
import re
from email.utils import format_datetime
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as xml_escape


# GitHub downloads the page through the Cloudflare Worker.
SITE_URL = "https://newalbumreleases-proxy.nikjin12345.workers.dev/"

# This remains the original source shown inside the RSS feed and index page.
SOURCE_PAGE_URL = "https://newalbumreleases.net/category/cat/"

SITE_TITLE = "New Album Releases - Archive"
SITE_DESCRIPTION = "Latest album posts from New Album Releases"

OUT_DIR = Path("site")
FEED_FILE = OUT_DIR / "Archive.xml"
INDEX_FILE = OUT_DIR / "index.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

POST_RE = re.compile(
    r'<div class="single" id="post-(?P<id>\d+)">.*?'
    r'<h2><a href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a></h2>.*?'
    r'<div class="date">.*?On (?P<month>[A-Za-z]+) - '
    r'(?P<day>\d{1,2}) - (?P<year>\d{4})</div>',
    re.S | re.I,
)


def fetch_text(url: str) -> str:
    """Download and decode the source HTML."""
    req = Request(url, headers=HEADERS)

    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_posts(page_html: str) -> list[dict]:
    """Extract album post details from the archive page."""
    posts: list[dict] = []

    for match in POST_RE.finditer(page_html):
        title = html.unescape(
            re.sub(r"<[^>]+>", "", match.group("title"))
        ).strip()

        link = html.unescape(match.group("link")).strip()
        post_id = match.group("id").strip()

        date_text = (
            f"{match.group('month')} "
            f"{match.group('day')} "
            f"{match.group('year')}"
        )

        pub_dt = dt.datetime.strptime(
            date_text,
            "%B %d %Y",
        ).replace(tzinfo=dt.timezone.utc)

        posts.append(
            {
                "id": post_id,
                "title": title,
                "link": link,
                "pub_dt": pub_dt,
            }
        )

    return posts


def cdata(text: str) -> str:
    """Safely wrap text in an XML CDATA section."""
    return "<![CDATA[" + text.replace(
        "]]>",
        "]]]]><![CDATA[>",
    ) + "]]>"


def build_rss(posts: list[dict]) -> str:
    """Create the RSS 2.0 document."""
    last_build = format_datetime(
        dt.datetime.now(dt.timezone.utc)
    )

    items_xml: list[str] = []

    for post in posts:
        title = post["title"]
        link = post["link"]
        post_id = post["id"]
        pub_date = format_datetime(post["pub_dt"])

        description = (
            f"New Album Releases archive post: {title}"
        )

        items_xml.append(
            f"""
    <item>
      <title>{xml_escape(title)}</title>
      <link>{xml_escape(link)}</link>
      <guid isPermaLink="false">{xml_escape(str(post_id))}</guid>
      <pubDate>{xml_escape(pub_date)}</pubDate>
      <description>{cdata(description)}</description>
    </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{xml_escape(SITE_TITLE)}</title>
    <link>{xml_escape(SOURCE_PAGE_URL)}</link>
    <description>{xml_escape(SITE_DESCRIPTION)}</description>
    <lastBuildDate>{xml_escape(last_build)}</lastBuildDate>
    <language>en-us</language>
{''.join(items_xml)}
  </channel>
</rss>
"""


def build_index() -> str:
    """Create the simple GitHub Pages index page."""
    source_url = html.escape(SOURCE_PAGE_URL)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{html.escape(SITE_TITLE)}</title>
  </head>
  <body>
    <h1>{html.escape(SITE_TITLE)}</h1>
    <p><a href="Archive.xml">Archive.xml</a></p>
    <p>
      Source:
      <a href="{source_url}">{source_url}</a>
    </p>
  </body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    page_html = fetch_text(SITE_URL)
    posts = parse_posts(page_html)

    if not posts:
        raise RuntimeError(
            "The source page downloaded successfully, "
            "but no album posts were found."
        )

    FEED_FILE.write_text(
        build_rss(posts),
        encoding="utf-8",
    )

    INDEX_FILE.write_text(
        build_index(),
        encoding="utf-8",
    )

    print(f"Downloaded source through: {SITE_URL}")
    print(f"Found {len(posts)} album posts.")
    print(f"Wrote {FEED_FILE} and {INDEX_FILE}")


if __name__ == "__main__":
    main()
