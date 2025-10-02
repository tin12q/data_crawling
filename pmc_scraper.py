"""
pmc_scraper.py
================

This module provides a command‐line tool for downloading and parsing the full
text of PubMed Central (PMC) articles listed in a CSV file.  The CSV file
should have at least two columns: ``Title`` and ``Link``.  Each ``Link`` must
contain a PMC identifier (e.g. ``https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4136787/``).

The tool uses the PMC BioC REST API to retrieve articles in JSON format.  It
extracts common article sections (e.g. ``abstract``, ``introduction``,
``methods``, ``results``, ``discussion``, ``conclusion``) by grouping
passages according to their ``section_type`` metadata.  Keywords are pulled
from passages whose ``section_type`` contains ``kw`` (keyword section types
vary across journals).  References are collected from passages where
``section_type`` equals ``REF`` and ``type`` equals ``ref``.  Each
reference’s title and author list are stored separately.

The resulting records are written to a JSON file.  Each record is a
dictionary with the following keys:

``pmcid``
    The PMC identifier (e.g. ``PMC4136787``).

``title``
    The article title.

``abstract``
    Text from the abstract.

``introduction``
    Text from the introduction section.

``methods``
    Text from the methods section (may include “Materials and Methods” or
    other variants).

``results``
    Text from the results section.

``discussion``
    Text from the discussion section.

``conclusion``
    Text from the conclusion section (may include “Conclusions/Significance” or
    “Concluding Remarks”).

``keywords``
    A list of keywords extracted from keyword sections.

``citations``
    A list of dictionaries, each containing ``title`` and ``authors`` for a
    reference.

Usage
-----

Run the script from the command line, providing the path to the CSV file and
the desired output JSON file:

```
python pmc_scraper.py --csv SB_publication_PMC.csv --out articles.json
```

If you wish to limit the number of articles processed (for testing
purposes), use ``--max N``.  Use ``--verbose`` to print progress messages.

This script requires the external ``requests`` library.  Install it via
``pip install requests`` if necessary.
"""

import argparse
import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import time

import pandas as pd
import requests


HTML_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PMCKeywordBot/1.0; +https://www.ncbi.nlm.nih.gov/pmc/)"
}
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def extract_pmcid(link: str) -> Optional[str]:
    """Extract the PMC identifier from a URL.

    Parameters
    ----------
    link: str
        A URL containing a PMC ID (e.g. ``https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4136787/``).

    Returns
    -------
    Optional[str]
        The PMC ID if found, otherwise ``None``.
    """
    match = re.search(r"PMC\d+", link)
    return match.group(0) if match else None


def fetch_bioc_json(pmcid: str) -> Dict:
    """Fetch BioC JSON for a given PMC ID.

    Parameters
    ----------
    pmcid: str
        A PMC identifier (e.g. ``PMC4136787``).

    Returns
    -------
    dict
        Parsed JSON from the BioC service.

    Raises
    ------
    requests.HTTPError
        If the HTTP request fails.
    ValueError
        If the response content cannot be parsed as JSON.
    """
    url = f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmcid}/unicode"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def merge_section_text(passages: List[Dict], section_types: List[str]) -> str:
    """Concatenate text from passages whose section_type is in ``section_types``.

    Parameters
    ----------
    passages: list of dict
        List of BioC passages.
    section_types: list of str
        Section type labels to include (case-insensitive).

    Returns
    -------
    str
        Joined text, separated by blank lines.
    """
    texts = []
    stypes = {s.upper() for s in section_types}
    for p in passages:
        stype = p.get("infons", {}).get("section_type", "").upper()
        if stype in stypes:
            text = p.get("text")
            if text:
                texts.append(text.strip())
    return "\n\n".join(texts)


def extract_keywords(passages: List[Dict]) -> List[str]:
    """Extract keywords from keyword passages.

    Keywords may appear in passages with ``section_type`` values like ``KW``,
    ``KEYWORD``, ``KEYWORDS``, or other variants.  Each keyword is assumed to
    occupy a separate passage or be separated by semicolons/commas within a
    passage.

    Parameters
    ----------
    passages: list of dict
        List of BioC passages.

    Returns
    -------
    list of str
        A list of cleaned keyword strings.
    """
    keywords: List[str] = []
    for p in passages:
        stype = p.get("infons", {}).get("section_type", "").upper()
        if stype in {"KW", "KEYWORD", "KEYWORDS"}:
            text = p.get("text", "")
            # Split on common delimiters
            for kw in re.split(r"[;,\n]\s*", text):
                kw = kw.strip()
                if kw:
                    keywords.append(kw)
    return keywords


class _MetaKeywordsParser(HTMLParser):
    """HTML parser that collects PMC ``citation_keywords`` meta content."""

    def __init__(self) -> None:
        super().__init__()
        self.keywords: List[str] = []

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        if tag.lower() != "meta":
            return
        attr_map = {name.lower(): value for name, value in attrs if name}
        if attr_map.get("name", "").lower() != "citation_keywords":
            return
        content = attr_map.get("content")
        if not content:
            return
        for kw in re.split(r"[;,\n]\s*", unescape(content)):
            kw = kw.strip()
            if kw:
                self.keywords.append(kw)


def fetch_html_keywords(url: str, timeout: int = 15) -> List[str]:
    """Download PMC article page HTML and extract ``citation_keywords`` entries."""
    try:
        response = requests.get(url, timeout=timeout, headers=HTML_REQUEST_HEADERS)
        response.raise_for_status()
    except requests.RequestException:
        return []
    parser = _MetaKeywordsParser()
    parser.feed(response.text)
    parser.close()
    return parser.keywords


def fetch_xml_keywords(pmcid: str, timeout: int = 15, retries: int = 3, backoff: float = 1.0) -> List[str]:
    """Fetch article metadata via EFetch and extract ``kwd`` entries."""
    pmc_param = pmcid[3:] if pmcid.upper().startswith("PMC") else pmcid
    attempt = 0
    while True:
        try:
            response = requests.get(
                EFETCH_URL,
                params={"db": "pmc", "id": pmc_param, "retmode": "xml"},
                timeout=timeout,
                headers={"User-Agent": HTML_REQUEST_HEADERS["User-Agent"]},
            )
            response.raise_for_status()
            break
        except requests.RequestException:
            attempt += 1
            if attempt >= retries:
                return []
            time.sleep(backoff * attempt)
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []
    keywords: List[str] = []
    # Prefer explicit keyword tags first.
    for kw_element in root.findall(".//kwd"):
        text = "".join(kw_element.itertext()).strip()
        if text:
            keywords.append(text)
    # Fall back to MeSH descriptor names, which are typically curated keywords.
    for mesh_descriptor in root.findall(".//mesh-heading/descriptor-name"):
        text = (mesh_descriptor.text or "").strip()
        if text:
            keywords.append(text)
    # Finally, include subject headings when other keyword sources are absent.
    for subject in root.findall(".//subject"):
        text = (subject.text or "").strip()
        if text:
            keywords.append(text)
    return keywords


def dedupe_keywords(*keyword_lists: List[str]) -> List[str]:
    """Merge multiple keyword lists, preserving order and removing duplicates."""
    seen = set()
    merged: List[str] = []
    for kw_list in keyword_lists:
        for kw in kw_list:
            normalized = kw.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
    return merged


def extract_citations(passages: List[Dict]) -> List[Dict[str, object]]:
    """Extract citations (references) from a list of passages.

    Each citation is represented by a passage with ``section_type`` equal to
    ``REF`` and ``type`` equal to ``ref``.  The passage text contains the title
    of the referenced work.  Author names are stored in the ``infons``
    dictionary with keys ``name_0``, ``name_1``, etc., each formatted as
    ``surname:Surname;given-names:Given Names``.

    Parameters
    ----------
    passages: list of dict
        List of BioC passages.

    Returns
    -------
    list of dict
        List of citation dictionaries with ``title`` and ``authors`` keys.
    """
    citations: List[Dict[str, object]] = []
    for p in passages:
        infons = p.get("infons", {})
        if infons.get("section_type", "").upper() == "REF" and infons.get("type", "") == "ref":
            title = p.get("text", "").strip()
            authors: List[str] = []
            # Extract author names
            for key, value in infons.items():
                if key.startswith("name_"):
                    try:
                        parts = dict(item.split(":", 1) for item in value.split(";"))
                    except Exception:
                        parts = {}
                    surname = parts.get("surname", "").strip()
                    given_names = parts.get("given-names", "").strip()
                    full_name = f"{given_names} {surname}".strip()
                    authors.append(full_name)
            citations.append({"title": title, "authors": authors})
    return citations


def parse_document(doc: Dict) -> Dict[str, object]:
    """Parse a single BioC document into a structured record.

    Parameters
    ----------
    doc: dict
        A BioC document dictionary.

    Returns
    -------
    dict
        Structured article record.
    """
    passages = doc.get("passages", [])
    record: Dict[str, object] = {}
    pmcid = doc.get("id") or doc.get("infons", {}).get("article-id_pmc")
    record["pmcid"] = pmcid
    # Extract title from TITLE/front passage
    title = ""
    for p in passages:
        infons = p.get("infons", {})
        if infons.get("section_type", "").upper() == "TITLE":
            t = p.get("text")
            if t:
                title = t.strip()
                break
    record["title"] = title
    # Sections
    record["abstract"] = merge_section_text(passages, ["ABSTRACT"])
    record["introduction"] = merge_section_text(passages, ["INTRO", "BACKGROUND"])
    record["methods"] = merge_section_text(passages, ["METHODS", "MATERIALS AND METHODS", "METHODOLOGY"])
    record["results"] = merge_section_text(passages, ["RESULTS", "FINDINGS"])
    record["discussion"] = merge_section_text(passages, ["DISCUSSION"])
    record["conclusion"] = merge_section_text(passages, ["CONCLUSION", "CONCLUSIONS", "CONCLUSIONS/SIGNIFICANCE", "CONCLUDING REMARKS"])
    # Keywords
    record["keywords"] = extract_keywords(passages)
    # Citations
    record["citations"] = extract_citations(passages)
    return record


def process_articles(csv_path: Path, out_path: Path, max_articles: Optional[int] = None, verbose: bool = False) -> None:
    """Process articles from a CSV file and write structured JSON records.

    Parameters
    ----------
    csv_path: Path
        Path to the input CSV file.

    out_path: Path
        Path to the output JSON file.

    max_articles: Optional[int], optional
        Maximum number of articles to process (for testing).  If ``None``, all
        articles are processed.

    verbose: bool, optional
        If ``True``, print progress messages.
    """
    df = pd.read_csv(csv_path)
    records: List[Dict[str, object]] = []
    xml_keyword_cache: Dict[str, List[str]] = {}
    html_keyword_cache: Dict[str, List[str]] = {}
    total = len(df) if max_articles is None else min(len(df), max_articles)
    for idx, row in df.iterrows():
        if max_articles is not None and idx >= max_articles:
            break
        link = row.get("Link", "")
        pmcid = extract_pmcid(link)
        if not pmcid:
            if verbose:
                print(f"[{idx + 1}/{total}] Skipping row without PMCID: {link}")
            continue
        if verbose:
            print(f"[{idx + 1}/{total}] Fetching {pmcid}...")
        xml_keywords: List[str] = []
        if pmcid:
            cached_xml = xml_keyword_cache.get(pmcid)
            if cached_xml is None:
                cached_xml = fetch_xml_keywords(pmcid)
                xml_keyword_cache[pmcid] = cached_xml
                if verbose:
                    if cached_xml:
                        print(f"    Retrieved {len(cached_xml)} keywords via EFetch.")
                    else:
                        print("    No keywords found via EFetch.")
            xml_keywords = cached_xml
        html_keywords: List[str] = []
        if not xml_keywords and isinstance(link, str) and link:
            cached_html = html_keyword_cache.get(link)
            if cached_html is None:
                cached_html = fetch_html_keywords(link)
                html_keyword_cache[link] = cached_html
                if verbose:
                    if cached_html:
                        print(f"    Retrieved {len(cached_html)} keywords from HTML metadata.")
                    else:
                        print("    No keywords found in HTML metadata.")
            html_keywords = cached_html
        try:
            bioc = fetch_bioc_json(pmcid)
        except requests.HTTPError as e:
            if verbose:
                print(f"Failed to fetch {pmcid}: {e}")
            continue
        except Exception as e:
            if verbose:
                print(f"Unexpected error fetching {pmcid}: {e}")
            continue
        # Each result is a list of collections; we expect one collection containing documents
        try:
            collections = bioc if isinstance(bioc, list) else [bioc]
            for col in collections:
                documents = col.get("documents", [])
                for doc in documents:
                    record = parse_document(doc)
                    record["keywords"] = dedupe_keywords(
                        record.get("keywords", []), xml_keywords, html_keywords
                    )
                    record["original_title"] = row.get("Title", "")
                    records.append(record)
        except Exception as e:
            if verbose:
                print(f"Error parsing {pmcid}: {e}")
            continue
    # Write out JSON
    out_path = Path(out_path)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    if verbose:
        print(f"Wrote {len(records)} records to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape PMC articles from a CSV using the BioC API.")
    parser.add_argument("--csv", type=Path, required=True, help="Path to the input CSV file")
    parser.add_argument("--out", type=Path, required=True, help="Path to the output JSON file")
    parser.add_argument("--max", type=int, default=None, help="Maximum number of articles to process (for testing)")
    parser.add_argument("--verbose", action="store_true", help="Print progress messages")
    args = parser.parse_args()
    process_articles(args.csv, args.out, max_articles=args.max, verbose=args.verbose)


if __name__ == "__main__":
    main()
