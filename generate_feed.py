from __future__ import annotations

import datetime as dt
import html
import re
from email.utils import format_datetime
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as xml_escape


# GitHub retrieves the page through Cloudflare.
FETCH_URL = "https://newalbumreleases-proxy.nikjin12345.workers.dev/"

# Original page shown in the RSS feed.
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
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# Finds a post container even when the id and class attributes
# appear in a different order.
POST_START_RE = re.compile(
    r"""
    <div\b
    (?=[^>]*\bid=["']post-(?P<id>\d+)["'])
    (?=[^>]*\bclass=["'][^"']*\bsingle\b[^"']*["'])
    [^>]*>
    """,
    re.I | re.X,
)

TITLE_RE = re.compile(
    r"""
    <h2\b[^>]*>
    \s*
    <a\b
    [^>]*\bhref=["'](?P<link>[^"']+)["']
    [^>]*>
    (?P<title>.*?)
    </a>
    \s*
    </h2>
    """,
    re.I | re.S | re.X,
)

DATE_RE = re.compile(
    r"""
    <div\b
    [^>]*\bclass=["'][^"']*\bdate\b[^"']*["']
    [^>]*>
    .*?
    \bOn\s+
    (?P<month>[A-Za-z]+)
    \s*-\s*
    (?P<day>\d{1,2})
    \s*-\s*
    (?P<year>\d{4})
    .*?
    </div>
    """,
    re.I | re.S | re.X,
)


def fetch_text(url: str) -> str:
    """Download and decode the source HTML."""
    request = Request(url, headers=HEADERS)

    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_text(value: str) -> str:
    """Remove HTML tags, decode entities and normalise spaces."""
    without_tags = re.sub(r"<[^>]+>", "", value)

    return html.unescape(without_tags).replace("\xa0", " ").strip()


def parse_posts(page_html: str) -> list[dict]:
    """Extract album posts from the archive page."""
    posts: list[dict] = []
    starts = list(POST_START_RE.finditer(page_html))

    print(f"Found {len(starts)} potential post containers.")

    for index, start_match in enumerate(starts):
        block_start = start_match.start()

        if index + 1 < len(starts):
            block_end = starts[index + 1].start()
        else:
            block_end = len(page_html)

        post_html = page_html[block_start:block_end]

        title_match = TITLE_RE.search(post_html)
        date_match = DATE_RE.search(post_html)

        if not title_match:
            print(
                "Skipping post "
                f"{start_match.group('id')}: title was not found."
            )
            continue

        if not date_match:
            print(
                "Skipping post "
                f"{start_match.group('id')}: date was not found."
            )
            continue

        post_id = start_match.group("id").strip()
        title = clean_text(title_match.group("title"))
        link = html.unescape(title_match.group("link")).strip()

        date_text = (
            f"{date_match.group('month')} "
            f"{date_match.group('day')} "
            f"{date_match.group('year')}"
        )

        try:
            pub_dt = dt.datetime.strptime(
                date_text,
                "%B %d %Y",
            ).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            print(
                f"Skipping post {post_id}: "
                f"unrecognised date {date_text!r}."
            )
            continue

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
    return (
        "<![CDATA["
        + text.replace("]]>", "]]]]><![CDATA[>")
        + "]]>"
    )


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
    """Create the GitHub Pages index."""
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

    page_html = fetch_text(FETCH_URL)

    print(f"Downloaded {len(page_html)} characters.")
    print(f"Downloaded through: {FETCH_URL}")

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

    print(f"Successfully parsed {len(posts)} album posts.")
    print(f"Wrote {FEED_FILE} and {INDEX_FILE}")


if __name__ == "__main__":
    main()
