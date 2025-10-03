#!/usr/bin/env python3
"""Download representative figure images for PMC articles listed in articles.json.

The script visits the public PMC landing page for each PMCID, extracts image
URLs (typically figure thumbnails) and downloads a configurable number per
article.  Results are written to an output directory and a manifest summarising
which files were saved.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Iterable, List, Sequence

import requests
from bs4 import BeautifulSoup

BASE_ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
DEFAULT_USER_AGENT = "PMCImageFetcher/1.0 (mailto:tin12q@example.com)"
DEFAULT_DELAY = 0.5  # seconds between article fetches to be polite
DEFAULT_IMAGES_PER_ARTICLE = 0  # 0 means "no limit"


def load_articles(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def build_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    return session


def parse_image_urls(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")

    urls: List[str] = []
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = base_url.rstrip("/") + src
        elif src.startswith("http"):
            pass
        else:
            # relative path without leading slash
            src = base_url + src

        if (
            any(token in src for token in ("/pmc/articles/", "/pmc/blobs/"))
            and any(ext in src.lower() for ext in (".jpg", ".jpeg", ".png", ".gif", ".tif"))
        ):
            urls.append(src)

    return urls


def download_image(session: requests.Session, url: str, dest: Path) -> bool:
    try:
        resp = session.get(url, timeout=45)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Failed to download {url}: {exc}", file=sys.stderr)
        return False

    if not dest.suffix:
        content_type = resp.headers.get("Content-Type", "")
        if "png" in content_type:
            dest = dest.with_suffix(".png")
        elif "gif" in content_type:
            dest = dest.with_suffix(".gif")
        else:
            dest = dest.with_suffix(".jpg")

    dest.write_bytes(resp.content)
    return True


def normalise_pmcid(pmcid: str) -> str:
    pmcid = pmcid.strip()
    if pmcid.upper().startswith("PMC"):
        return pmcid.upper()
    return f"PMC{pmcid}"


def fetch_images_for_pmcid(
    session: requests.Session,
    pmcid: str,
    output_dir: Path,
    max_images: int,
) -> List[str]:
    article_url = BASE_ARTICLE_URL.format(pmcid=pmcid)
    try:
        resp = session.get(article_url, timeout=45)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Failed to fetch article page for {pmcid}: {exc}", file=sys.stderr)
        return []

    base_url = "https://pmc.ncbi.nlm.nih.gov"
    image_urls = parse_image_urls(resp.text, base_url)
    if not image_urls:
        print(f"No images found for {pmcid}", file=sys.stderr)
        return []

    saved_urls: List[str] = []
    selected_urls = image_urls if max_images <= 0 else image_urls[:max_images]
    for index, url in enumerate(selected_urls, start=1):
        suffix = Path(url).suffix or ""
        dest = output_dir / f"{pmcid}_{index}{suffix}"
        if dest.exists():
            saved_urls.append(url)
            continue
        if download_image(session, url, dest):
            saved_urls.append(url)
    return saved_urls


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("articles.json"),
        help="Path to the articles JSON exported from the crawler (default: articles.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("article_images"),
        help="Directory where images will be saved (default: article_images)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of articles to process (default: all)",
    )
    parser.add_argument(
        "--per-article",
        type=int,
        default=DEFAULT_IMAGES_PER_ARTICLE,
        help="Maximum number of images to download per article (0 means all; default: %(default)s)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Delay in seconds between article requests to respect NCBI rate limits (default: %(default)s)",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="Custom User-Agent header for HTTP requests.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional path to write a JSON manifest of downloaded images.",
    )
    return parser.parse_args(argv)


def write_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    articles = load_articles(args.input)
    ensure_directory(args.output_dir)
    session = build_session(args.user_agent)

    manifest: dict[str, list[str]] = {}
    processed = 0

    for article in articles:
        if args.limit and processed >= args.limit:
            break
        pmcid = article.get("pmcid")
        if not pmcid:
            continue
        pmcid = normalise_pmcid(pmcid)

        saved = fetch_images_for_pmcid(
            session,
            pmcid,
            args.output_dir,
            args.per_article,
        )
        if saved:
            manifest[pmcid] = [str(path) for path in saved]
        processed += 1
        time.sleep(args.delay)

    if args.manifest:
        write_manifest(args.manifest, manifest)

    print(
        f"Processed {processed} articles; images saved for {len(manifest)} articles.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
