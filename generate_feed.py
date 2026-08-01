from __future__ import annotations

import datetime as dt
import html
import re
from email.utils import format_datetime
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as xml_escape

SITE_URL = "https://newalbumreleases.net/category/cat/"
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
    "Referer": "https://newalbumreleases.net/",
}

POST_RE = re.compile(
    r'<div class="single" id="post-(?P<id>\d+)">.*?'
    r'<h2><a href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a></h2>.*?'
    r'<div class="date">.*?On (?P<month>[A-Za-z]+) - (?P<day>\d{1,2}) - (?P<year>\d{4})</div>',
    re.S | re.I,
)


def fetch_text(url: str) -> str:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_posts(page_html: str) -> list[dict]:
    posts: list[dict] = []

    for m in POST_RE.finditer(page_html):
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group("title"))).strip()
        link = html.unescape(m.group("link")).strip()
        post_id = m.group("id").strip()

        date_text = f"{m.group('month')} {m.group('day')} {m.group('year')}"
        pub_dt = dt.datetime.strptime(date_text, "%B %d %Y").replace(tzinfo=dt.timezone.utc)

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
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def build_rss(posts: list[dict]) -> str:
    last_build = format_datetime(dt.datetime.now(dt.timezone.utc))

    items_xml = []
    for post in posts:
        title = post["title"]
        link = post["link"]
        post_id = post["id"]
        pub_date = format_datetime(post["pub_dt"])

        description = f"New Album Releases archive post: {title}"

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
    <link>{xml_escape(SITE_URL)}</link>
    <description>{xml_escape(SITE_DESCRIPTION)}</description>
    <lastBuildDate>{xml_escape(last_build)}</lastBuildDate>
    <language>en-us</language>
{''.join(items_xml)}
  </channel>
</rss>
"""


def build_index() -> str:
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>{html.escape(SITE_TITLE)}</title>
  </head>
  <body>
    <h1>{html.escape(SITE_TITLE)}</h1>
    <p><a href="Archive.xml">Archive.xml</a></p>
    <p>Source: <a href="{html.escape(SITE_URL)}">{html.escape(SITE_URL)}</a></p>
  </body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    page_html = fetch_text(SITE_URL)
    posts = parse_posts(page_html)
    FEED_FILE.write_text(build_rss(posts), encoding="utf-8")
    INDEX_FILE.write_text(build_index(), encoding="utf-8")
    print(f"Wrote {FEED_FILE} and {INDEX_FILE}")


if __name__ == "__main__":
    main()
