#!/usr/bin/env python3
"""Query arXiv for a keyword and print matching papers."""

import argparse
import json
import sys
import xml.etree.ElementTree as ET

try:
    import requests
except ImportError as exc:  # pragma: no cover - import-time dependency issue
    print(
        "Missing dependency: requests. Install it with `pip install requests`.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def fetch_arxiv_results(keyword: str, max_results: int) -> list[dict[str, str]]:
    params = {
        "search_query": f"all:{keyword}",
        "start": 0,
        "max_results": max_results,
    }
    response = requests.get(ARXIV_API_URL, params=params, timeout=15)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    entries = []

    for entry in root.findall("atom:entry", ATOM_NS):
        title = normalize_whitespace(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
        url = normalize_whitespace(entry.findtext("atom:id", default="", namespaces=ATOM_NS))
        published = normalize_whitespace(
            entry.findtext("atom:published", default="", namespaces=ATOM_NS)
        )
        summary = normalize_whitespace(
            entry.findtext("atom:summary", default="", namespaces=ATOM_NS)
        )

        entries.append(
            {
                "title": title,
                "url": url,
                "published": published,
                "summary": summary[:300] + ("..." if len(summary) > 300 else ""),
            }
        )

    return entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search arXiv papers by keyword.")
    parser.add_argument("--keyword", default="python", help="Keyword to search for.")
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum number of results to return.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def print_text_results(results: list[dict[str, str]]) -> None:
    for idx, item in enumerate(results, start=1):
        print(f"{idx}. {item['title']}")
        print(f"   URL: {item['url']}")
        print(f"   Published: {item['published']}")
        print(f"   Summary: {item['summary']}")
        print()


def main() -> int:
    args = parse_args()
    if args.max_results <= 0:
        print("--max-results must be greater than 0.", file=sys.stderr)
        return 1

    try:
        results = fetch_arxiv_results(args.keyword, args.max_results)
    except requests.RequestException as exc:
        print(f"Failed to query arXiv API: {exc}", file=sys.stderr)
        return 1
    except ET.ParseError as exc:
        print(f"Failed to parse arXiv response XML: {exc}", file=sys.stderr)
        return 1

    if not results:
        if args.format == "json":
            print("[]")
        else:
            print(f'No results found for keyword "{args.keyword}".')
        return 0

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print_text_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
