#!/usr/bin/env python3
"""Regenerate _posts/ entries from the Substack RSS feed.

Substack sits behind Cloudflare, which 403s GitHub Actions servers, so the
direct feed fetch only works locally. When it fails, the script falls back to
the rss2json mirror (https://rss2json.com), which fetches the feed from its
own servers and is reachable from Actions. Either way it writes one Markdown
stub per post that links out to Substack via the al-folio `redirect` field.

Runs automatically every day via .github/workflows/update-blog.yml.

Usage (from the repo root):
    python3 bin/update_blog.py           # regenerate _posts/
    python3 bin/update_blog.py --dry-run # print what would change, write nothing
"""
import os
import re
import json
import html
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import sys

FEED_URL = "https://probabilitasblog.substack.com/feed"
MIRROR_URL = "https://api.rss2json.com/v1/api.json?rss_url=" + urllib.parse.quote(FEED_URL, safe="")
SOURCE_NAME = "Probabilitas"
POSTS_DIR = "_posts"
NS = {"content": "http://purl.org/rss/1.0/modules/content/"}


def clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read()


def parse_direct(raw):
    items = []
    for it in ET.fromstring(raw).findall("./channel/item"):
        items.append(
            {
                "title": clean(it.findtext("title")),
                "link": (it.findtext("link") or "").strip(),
                "date": parsedate_to_datetime(it.findtext("pubDate")),
                "description": clean(it.findtext("description")),
                "content": clean(it.findtext("content:encoded", namespaces=NS)),
            }
        )
    return items


def parse_mirror(raw):
    data = json.loads(raw)
    if data.get("status") != "ok":
        raise RuntimeError(f"rss2json returned status {data.get('status')!r}: {data.get('message')}")
    items = []
    for it in data.get("items", []):
        # rss2json normalizes pubDate to "YYYY-MM-DD HH:MM:SS" in UTC
        dt = datetime.strptime(it.get("pubDate", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        items.append(
            {
                "title": clean(it.get("title")),
                "link": (it.get("link") or "").strip(),
                "date": dt,
                "description": clean(it.get("description")),
                "content": clean(it.get("content")),
            }
        )
    return items


def load_items():
    try:
        return parse_direct(fetch(FEED_URL))
    except Exception as e:
        print(f"Direct feed fetch failed ({e}); falling back to rss2json mirror")
        return parse_mirror(fetch(MIRROR_URL))


def main():
    dry_run = "--dry-run" in sys.argv
    items = load_items()
    print(f"{len(items)} posts in feed{' (dry run)' if dry_run else ''}:")

    if not dry_run:
        os.makedirs(POSTS_DIR, exist_ok=True)

    for it in items:
        title, link, dt = it["title"], it["link"], it["date"]
        if not title or not link:
            continue
        desc = it["description"]
        if len(desc) > 300:
            desc = desc[:297].rstrip() + "..."
        # Full article text (plain) drives the al-folio read-time estimate,
        # which is computed from feed_content. It is never rendered on the page.
        full_text = it["content"] or desc
        slug = re.sub(r"[^a-z0-9-]", "", link.rstrip("/").split("/")[-1].lower())
        fname = f"{dt.strftime('%Y-%m-%d')}-{slug}.md"
        content = (
            "---\n"
            "layout: post\n"
            f"title: {json.dumps(title)}\n"
            f"date: {dt.strftime('%Y-%m-%d %H:%M:%S %z')}\n"
            f"description: {json.dumps(desc)}\n"
            f"redirect: {link}\n"
            f"external_source: {SOURCE_NAME}\n"
            f"feed_content: {json.dumps(full_text)}\n"
            "---\n\n"
            f"{desc}\n\n"
            f"[Read the full post on Substack →]({link})\n"
        )
        print(f"  {fname}  -  {title}")
        if not dry_run:
            with open(os.path.join(POSTS_DIR, fname), "w") as f:
                f.write(content)


if __name__ == "__main__":
    main()
