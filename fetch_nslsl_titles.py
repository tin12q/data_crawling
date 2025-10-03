#!/usr/bin/env python3
"""Download publication titles from the NASA Space Life Sciences Library (NSLSL).

The script automates the public NSLSL search interface by issuing a broad
query (defaults to the simple term ``space``) and paginating through the
results in batches of up to 1,000 records per request.  For each publication it
collects the NSLSL identifier and the displayed title, optionally writing the
aggregate list to JSON and/or TSV files.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from typing import Iterable, List, Sequence

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://extapps.ksc.nasa.gov/NSLSL"
SEARCH_ROOT = f"{BASE_URL}/Search"
SEARCH_ENDPOINT = f"{SEARCH_ROOT}/SearchAjax"
FETCH_ENDPOINT = f"{SEARCH_ROOT}/FetchPageAjax"
DETAIL_URL_TEMPLATE = f"{SEARCH_ROOT}/DetailsForId/{{pub_id}}"
DEFAULT_USER_AGENT = "NSLSLTitleFetcher/1.0"

REQUEST_TIMEOUT = 120  # seconds
REQUEST_DELAY = 0.3    # courtesy pause between page fetches
MAX_RETRIES = 3

VALID_PAGE_SIZES = {10, 20, 50, 100, 200, 500, 1000}


@dataclass(frozen=True)
class Record:
    nslsl_id: str
    title: str

    @property
    def detail_url(self) -> str:
        return DETAIL_URL_TEMPLATE.format(pub_id=self.nslsl_id)


class NSLSLClient:
    """Lightweight helper around ``requests.Session`` for NSLSL search."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._token: str | None = None

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(SEARCH_ROOT, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                break
            except requests.RequestException as exc:  # noqa: PERF203 benign small map
                if attempt == MAX_RETRIES:
                    raise RuntimeError("Failed to load NSLSL search page") from exc
                backoff = REQUEST_DELAY * attempt
                time.sleep(backoff)
        soup = BeautifulSoup(resp.text, "html.parser")
        token_field = soup.select_one(
            'form#__AjaxAntiForgeryForm input[name="__RequestVerificationToken"]'
        )
        if not token_field or not token_field.get("value"):
            raise RuntimeError("Unable to find anti-forgery token on NSLSL search page")
        self._token = token_field["value"]
        return self._token

    def _post(self, endpoint: str, data: dict) -> BeautifulSoup:
        token = self._ensure_token()
        payload = {"__RequestVerificationToken": token}
        payload.update(data)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.post(endpoint, data=payload, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                break
            except requests.RequestException as exc:
                if attempt == MAX_RETRIES:
                    raise
                backoff = REQUEST_DELAY * attempt
                time.sleep(backoff)
        return BeautifulSoup(resp.text, "html.parser")

    def fetch_page(
        self,
        *,
        page: int,
        per_page: int,
        search_term: str,
        sort_by: str = "PubDate",
        sort_ascending: bool = True,
    ) -> tuple[List[Record], int, int]:
        """Return a page of search results with total counts and page count.

        Args:
            page: One-based page index.
            per_page: Number of items per page (allowed set defined by NSLSL UI).
            search_term: Value for the simple search field.
            sort_by: Field identifier to sort on (default mirrors UI).
            sort_ascending: ``True`` for ascending ordering; descending otherwise.

        Returns:
            A tuple ``(records, total_results, total_pages)`` where
            ``records`` holds ``Record`` instances for the requested page.
        """
        endpoint = SEARCH_ENDPOINT if page == 1 else FETCH_ENDPOINT
        data = {
            "model.PageFormat": "Summary",
            "model.CurrentPage": str(page),
            "model.SortBy": sort_by,
            "model.SearchCriteria": search_term,
            "model.NumberPerPage": str(per_page),
            "model.DefaultFilterCriteria": "",
            "model.SortAscending": str(sort_ascending).lower(),
            "model.SelectAllChecked": "false",
        }
        soup = self._post(endpoint, data)
        total_elem = soup.select_one("#searchResultCount")
        total_pages_elem = soup.select_one("#NumPages")
        if not total_elem or not total_pages_elem:
            raise RuntimeError("Unexpected response structure from NSLSL search")
        total_results = int(total_elem["value"])
        total_pages = int(total_pages_elem["value"])

        records: List[Record] = []
        for anchor in soup.select("a.pubDetail"):
            pub_id = (anchor.get("data-pubid") or "").strip()
            title = anchor.get_text(strip=True)
            if not pub_id or not title:
                continue
            records.append(Record(pub_id, title))
        return records, total_results, total_pages


def write_json(records: Sequence[Record], path: str) -> None:
    payload = [
        {
            "id": record.nslsl_id,
            "title": record.title,
            "detail_url": record.detail_url,
        }
        for record in records
    ]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def write_tsv(records: Sequence[Record], path: str | None) -> None:
    rows = [("id", "title", "detail_url")]
    rows.extend((rec.nslsl_id, rec.title, rec.detail_url) for rec in records)
    if path:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerows(rows)
    else:
        writer = csv.writer(sys.stdout, delimiter="\t")
        writer.writerows(rows)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--term",
        default="space",
        help="Search term to issue (default: %(default)s).",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=1000,
        choices=sorted(VALID_PAGE_SIZES),
        help="Number of results per request (choices mirror NSLSL UI).",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="Optional path to write the results as JSON array.",
    )
    parser.add_argument(
        "--tsv",
        metavar="PATH",
        help="Optional path to write the results as TSV (prints to stdout if omitted).",
    )
    parser.add_argument(
        "--no-stdout",
        action="store_true",
        help="Suppress TSV output to stdout when --tsv is not provided.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    client = NSLSLClient()

    per_page = args.per_page
    term = args.term

    print(f"Fetching NSLSL records for term '{term}' ({per_page} per page)...", file=sys.stderr)

    records: list[Record] = []
    seen_ids: set[str] = set()

    page = 1
    total_pages: int | None = None
    total_results: int | None = None

    while total_pages is None or page <= total_pages:
        try:
            page_records, total_results, total_pages = client.fetch_page(
                page=page,
                per_page=per_page,
                search_term=term,
            )
        except Exception as exc:  # noqa: BLE001 - surface unexpected issues
            print(f"Error fetching page {page}: {exc}", file=sys.stderr)
            return 1

        new_count = 0
        for rec in page_records:
            if rec.nslsl_id in seen_ids:
                continue
            seen_ids.add(rec.nslsl_id)
            records.append(rec)
            new_count += 1

        print(
            f"Page {page}/{total_pages} collected {new_count} records (total so far {len(records)}/{total_results})",
            file=sys.stderr,
        )

        page += 1
        if page <= total_pages:
            time.sleep(REQUEST_DELAY)

    if total_results is not None and len(records) != total_results:
        print(
            f"Warning: expected {total_results} records but captured {len(records)}.",
            file=sys.stderr,
        )

    if args.json:
        write_json(records, args.json)
        print(f"Wrote JSON output to {args.json}", file=sys.stderr)

    if args.tsv:
        write_tsv(records, args.tsv)
        print(f"Wrote TSV output to {args.tsv}", file=sys.stderr)
    elif not args.no_stdout:
        write_tsv(records, None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
