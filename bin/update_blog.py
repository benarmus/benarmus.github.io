#!/usr/bin/env python3
"""Regenerate _posts/ entries from the Substack RSS feed.

Substack sits behind Cloudflare, which 403s the GitHub Actions build server,
so posts can't be imported at build time. Instead this script runs locally
(where the feed is reachable) and writes one Markdown stub per post that links
out to Substack via the al-folio `redirect` field.

Usage (from the repo root):
    python3 bin/update_blog.py           # regenerate _posts/
    python3 bin/update_blog.py --dry-run # print what would change, write nothing

Then commit and push:
    git add _posts && git commit -m "Update blog from Substack" && git push
"""
import os
import re
import json
import html
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import sys

FEED_URL = "https://thequodlibet.substack.com/feed"
SOURCE_NAME = "Quodlibet"
POSTS_DIR = "_posts"
NS = {"content": "http://purl.org/rss/1.0/modules/content/"}


def clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def main():
    dry_run = "--dry-run" in sys.argv
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "Mozilla/5.0"})
    xml = urllib.request.urlopen(req, timeout=30).read()
    items = ET.fromstring(xml).findall("./channel/item")
    print(f"{len(items)} posts in feed{' (dry run)' if dry_run else ''}:")

    if not dry_run:
        os.makedirs(POSTS_DIR, exist_ok=True)

    for it in items:
        title = clean(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        dt = parsedate_to_datetime(it.findtext("pubDate"))
        desc = clean(it.findtext("description"))
        if len(desc) > 300:
            desc = desc[:297].rstrip() + "..."
        # Full article text (plain) drives the al-folio read-time estimate,
        # which is computed from feed_content. It is never rendered on the page.
        full_text = clean(it.findtext("content:encoded", namespaces=NS)) or desc
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
