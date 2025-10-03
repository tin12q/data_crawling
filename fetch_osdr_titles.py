#!/usr/bin/env python3
"""Fetch dataset titles from NASA's OSDR biological data API."""
from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path
from typing import Iterable, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover - optional dependency
    certifi = None

API_ROOT = "https://visualization.osdr.nasa.gov/biodata/api/"
TITLE_ENDPOINT = "v2/dataset/*/metadata/study%20title/"


SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()


def fetch_json(endpoint: str) -> dict:
    url = f"{API_ROOT}{endpoint}?format=json"
    request = Request(url, headers={"User-Agent": "OSDRTitleFetcher/1.0"})
    with urlopen(request, context=SSL_CONTEXT) as response:  # noqa: S310 - trusted NASA endpoint
        charset = response.headers.get_content_charset() or "utf-8"
        payload = response.read().decode(charset)
    return json.loads(payload)


def fetch_dataset_titles() -> List[Tuple[str, str]]:
    raw = fetch_json(TITLE_ENDPOINT)
    titles: List[Tuple[str, str]] = []
    for dataset_id, content in raw.items():
        metadata = content.get("metadata", {})
        title_value = metadata.get("study title")
        if isinstance(title_value, list):
            title = "; ".join(str(part).strip() for part in title_value if part)
        elif isinstance(title_value, str):
            title = title_value.strip()
        elif title_value is None:
            title = ""
        else:
            title = str(title_value)
        titles.append((dataset_id, title))
    titles.sort(key=lambda item: (item[0].startswith("OSD-"), item[0]))
    return titles


def write_json(titles: Iterable[Tuple[str, str]], output: Path) -> None:
    data = [{"id": ds_id, "title": title} for ds_id, title in titles]
    output.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_table(titles: Iterable[Tuple[str, str]], output: Path | None) -> None:
    lines = ["id\ttitle"]
    lines.extend(f"{ds_id}\t{title}" for ds_id, title in titles)
    text = "\n".join(lines)
    if output:
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        help="Optional path to save results as JSON array with objects {id, title}.",
    )
    parser.add_argument(
        "--tsv",
        type=Path,
        help="Optional path to save results as a tab-separated table (also printed to stdout if omitted).",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        titles = fetch_dataset_titles()
    except (HTTPError, URLError) as err:
        parser.error(f"Failed to fetch titles: {err}")
        return 2

    if args.json:
        write_json(titles, args.json)
    write_table(titles, args.tsv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
