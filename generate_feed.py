from __future__ import annotations

import datetime as dt
import html
import re
import time
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as xml_escape


# GitHub retrieves the page through the Cloudflare Worker.
PROXY_URL = "https://newalbumreleases-proxy.nikjin12345.workers.dev/"

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
    "Cache-Control": "no-cache, no-store, max-age=0",
    "Pragma": "no-cache",
}


# Finds a post container even when id and class attributes
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


def build_fetch_url() -> str:
    """Create a unique proxy URL to bypass cached copies."""
    cache_value = int(time.time())

    return f"{PROXY_URL}?{urlencode({'cache': cache_value})}"


def fetch_text(url: str) -> str:
    """Download and decode the source HTML."""
    request = Request(
        url,
        headers=HEADERS,
        method="GET",
    )

    with urlopen(request, timeout=60) as response:
        status = getattr(response, "status", 200)

        if status != 200:
            raise RuntimeError(
                f"Proxy returned HTTP {status}."
            )

        raw_data = response.read()

        print(
            "Proxy response headers:"
        )

        for header_name in (
            "date",
            "age",
            "cache-control",
            "cf-cache-status",
            "content-type",
        ):
            header_value = response.headers.get(header_name)

            if header_value:
                print(
                    f"  {header_name}: {header_value}"
                )

        return raw_data.decode(
            "utf-8",
            errors="replace",
        )


def clean_text(value: str) -> str:
    """Remove HTML tags, decode entities and normalise spaces."""
    without_tags = re.sub(
        r"<[^>]+>",
        "",
        value,
    )

    decoded = html.unescape(without_tags)

    return re.sub(
        r"\s+",
        " ",
        decoded.replace("\xa0", " "),
    ).strip()


def normalise_link(link: str) -> str:
    """Convert source links into clean absolute URLs."""
    cleaned = html.unescape(link).strip()

    if cleaned.startswith("//"):
        return "https:" + cleaned

    if cleaned.startswith("/"):
        return "https://newalbumreleases.net" + cleaned

    return cleaned


def parse_posts(page_html: str) -> list[dict]:
    """Extract album posts from the archive page."""
    parsed_posts: list[dict] = []
    starts = list(POST_START_RE.finditer(page_html))

    print(
        f"Found {len(starts)} potential post containers."
    )

    for index, start_match in enumerate(starts):
        block_start = start_match.start()

        if index + 1 < len(starts):
            block_end = starts[index + 1].start()
        else:
            block_end = len(page_html)

        post_html = page_html[block_start:block_end]

        title_match = TITLE_RE.search(post_html)
        date_match = DATE_RE.search(post_html)

        post_id = start_match.group("id").strip()

        if not title_match:
            print(
                f"Skipping post {post_id}: "
                "title was not found."
            )
            continue

        if not date_match:
            title_preview = clean_text(
                title_match.group("title")
            )

            print(
                f"Skipping post {post_id} "
                f"({title_preview}): date was not found."
            )
            continue

        title = clean_text(
            title_match.group("title")
        )

        link = normalise_link(
            title_match.group("link")
        )

        date_text = (
            f"{date_match.group('month')} "
            f"{date_match.group('day')} "
            f"{date_match.group('year')}"
        )

        try:
            pub_dt = dt.datetime.strptime(
                date_text,
                "%B %d %Y",
            ).replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            print(
                f"Skipping post {post_id}: "
                f"unrecognised date {date_text!r}."
            )
            continue

        if not title or not link:
            print(
                f"Skipping post {post_id}: "
                "title or link was empty."
            )
            continue

        parsed_posts.append(
            {
                "id": post_id,
                "title": title,
                "link": link,
                "pub_dt": pub_dt,
            }
        )

    return deduplicate_and_sort_posts(
        parsed_posts
    )


def deduplicate_and_sort_posts(
    posts: list[dict],
) -> list[dict]:
    """Remove duplicate IDs/links and place newest posts first."""
    unique_posts: list[dict] = []

    seen_ids: set[str] = set()
    seen_links: set[str] = set()

    for post in posts:
        post_id = str(post["id"])
        link = str(post["link"])

        if (
            post_id in seen_ids
            or link in seen_links
        ):
            print(
                "Skipping duplicate post: "
                f"{post['title']} ({link})"
            )
            continue

        seen_ids.add(post_id)
        seen_links.add(link)
        unique_posts.append(post)

    unique_posts.sort(
        key=lambda post: (
            post["pub_dt"],
            int(post["id"]),
        ),
        reverse=True,
    )

    return unique_posts


def cdata(text: str) -> str:
    """Safely wrap text in an XML CDATA section."""
    safe_text = text.replace(
        "]]>",
        "]]]]><![CDATA[>",
    )

    return f"<![CDATA[{safe_text}]]>"


def build_rss(posts: list[dict]) -> str:
    """Create the RSS 2.0 document."""
    last_build = format_datetime(
        dt.datetime.now(dt.timezone.utc)
    )

    items_xml: list[str] = []

    for post in posts:
        title = str(post["title"])
        link = str(post["link"])
        post_id = str(post["id"])

        pub_date = format_datetime(
            post["pub_dt"]
        )

        description = (
            "New Album Releases archive post: "
            f"{title}"
        )

        items_xml.append(
            f"""
    <item>
      <title>{xml_escape(title)}</title>
      <link>{xml_escape(link)}</link>
      <guid isPermaLink="false">{xml_escape(post_id)}</guid>
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
    source_url = html.escape(
        SOURCE_PAGE_URL
    )

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
    OUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fetch_url = build_fetch_url()

    print(
        f"Downloading through: {fetch_url}"
    )

    page_html = fetch_text(
        fetch_url
    )

    print(
        f"Downloaded {len(page_html)} characters."
    )

    posts = parse_posts(
        page_html
    )

    if not posts:
        raise RuntimeError(
            "The source page downloaded successfully, "
            "but no album posts were found."
        )

    print(
        f"Successfully parsed {len(posts)} unique album posts."
    )

    print(
        "First five feed entries:"
    )

    for post in posts[:5]:
        print(
            f"- {post['title']} | "
            f"{post['pub_dt'].date()} | "
            f"{post['link']}"
        )

    FEED_FILE.write_text(
        build_rss(posts),
        encoding="utf-8",
    )

    INDEX_FILE.write_text(
        build_index(),
        encoding="utf-8",
    )

    print(
        f"Wrote {FEED_FILE} and {INDEX_FILE}"
    )


if __name__ == "__main__":
    main()
