from __future__ import annotations

import datetime as dt
import html
import json
from email.utils import format_datetime
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as xml_escape

API_URL = "https://newalbumreleases.net/wp-json/wp/v2/posts?categories=34&per_page=20&orderby=date&order=desc&_fields=id,date,date_gmt,link,title,excerpt,content,modified"

SITE_TITLE = "New Album Releases - Archive"
SITE_LINK = "https://newalbumreleases.net/category/cat/"
SITE_DESCRIPTION = "Latest album posts from New Album Releases"

OUT_DIR = Path("site")
FEED_FILE = OUT_DIR / "feed.xml"
INDEX_FILE = OUT_DIR / "index.html"


def fetch_json(url: str):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_iso(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def build_rss(posts: list[dict]) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    last_build = format_datetime(now)

    items_xml = []
    for post in posts:
        title = html.unescape(post.get("title", {}).get("rendered", "")).strip()
        link = post.get("link", "").strip()
        post_id = post.get("id")
        pub_dt = parse_iso(post.get("date_gmt") or post.get("date"))
        pub_date = format_datetime(pub_dt.astimezone(dt.timezone.utc))
        excerpt = post.get("excerpt", {}).get("rendered", "") or ""
        content = post.get("content", {}).get("rendered", "") or ""

        items_xml.append(
            f"""
    <item>
      <title>{xml_escape(title)}</title>
      <link>{xml_escape(link)}</link>
      <guid isPermaLink="false">{xml_escape(str(post_id))}</guid>
      <pubDate>{xml_escape(pub_date)}</pubDate>
      <description>{cdata(excerpt)}</description>
      <content:encoded>{cdata(content)}</content:encoded>
    </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{xml_escape(SITE_TITLE)}</title>
    <link>{xml_escape(SITE_LINK)}</link>
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
    <p><a href="feed.xml">RSS feed</a></p>
    <p>Source: <a href="{html.escape(SITE_LINK)}">{html.escape(SITE_LINK)}</a></p>
  </body>
</html>
"""


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    posts = fetch_json(API_URL)
    FEED_FILE.write_text(build_rss(posts), encoding="utf-8")
    INDEX_FILE.write_text(build_index(), encoding="utf-8")
    print(f"Wrote {FEED_FILE} and {INDEX_FILE}")


if __name__ == "__main__":
    main()
