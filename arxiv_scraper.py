import json
import sys
import xml.etree.ElementTree as ET
import requests


ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper"


def fetch_arxiv_paper(paper_id: str) -> dict | None:
    params = {"id_list": paper_id}
    response = requests.get(ARXIV_API_URL, params=params, timeout=15)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    entry = root.find("atom:entry", ATOM_NS)

    if entry is None:
        return None

    title = normalize_whitespace(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
    url = normalize_whitespace(entry.findtext("atom:id", default="", namespaces=ATOM_NS))
    published = normalize_whitespace(
        entry.findtext("atom:published", default="", namespaces=ATOM_NS)
    )
    summary = normalize_whitespace(
        entry.findtext("atom:summary", default="", namespaces=ATOM_NS)
    )
    authors = [
        normalize_whitespace(a.findtext("atom:name", default="", namespaces=ATOM_NS))
        for a in entry.findall("atom:author", ATOM_NS)
    ]

    return {
        "title": title,
        "url": url,
        "published": published,
        "authors": authors,
        "summary": summary,
    }


def fetch_arxiv_papers_batch(paper_ids: list[str]) -> dict[str, dict]:
    """Fetch metadata for multiple arXiv papers in one request."""
    if not paper_ids:
        return {}
    params = {"id_list": ",".join(paper_ids), "max_results": len(paper_ids)}
    response = requests.get(ARXIV_API_URL, params=params, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    results = {}
    for entry in root.findall("atom:entry", ATOM_NS):
        entry_id = normalize_whitespace(entry.findtext("atom:id", default="", namespaces=ATOM_NS))
        # Extract the arXiv ID from the full URL (e.g. http://arxiv.org/abs/1706.03762v5 -> 1706.03762)
        arxiv_id = entry_id.split("/abs/")[-1].split("v")[0] if "/abs/" in entry_id else entry_id
        title = normalize_whitespace(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
        if not title or title.startswith("Error"):
            continue
        results[arxiv_id] = {
            "title": title,
            "url": entry_id,
            "published": normalize_whitespace(
                entry.findtext("atom:published", default="", namespaces=ATOM_NS)
            ),
            "authors": [
                normalize_whitespace(a.findtext("atom:name", default="", namespaces=ATOM_NS))
                for a in entry.findall("atom:author", ATOM_NS)
            ],
            "summary": normalize_whitespace(
                entry.findtext("atom:summary", default="", namespaces=ATOM_NS)
            ),
        }
    return results


def fetch_references(paper_id: str) -> list[dict]:
    """Fetch referenced papers via Semantic Scholar, enriched with arXiv metadata."""
    url = f"{SEMANTIC_SCHOLAR_API_URL}/ArXiv:{paper_id}"
    params = {"fields": "references.title,references.externalIds,references.url"}
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    refs = []
    arxiv_ids = []
    for ref in data.get("references", []):
        ext_ids = ref.get("externalIds") or {}
        entry = {"title": ref.get("title", "")}
        if ext_ids.get("ArXiv"):
            entry["arxiv_id"] = ext_ids["ArXiv"]
            entry["arxiv_url"] = f"https://arxiv.org/abs/{ext_ids['ArXiv']}"
            arxiv_ids.append(ext_ids["ArXiv"])
        if ext_ids.get("DOI"):
            entry["doi_url"] = f"https://doi.org/{ext_ids['DOI']}"
        if ref.get("url"):
            entry["semantic_scholar_url"] = ref["url"]
        refs.append(entry)

    # Batch-fetch arXiv metadata for all references that have arXiv IDs
    if arxiv_ids:
        try:
            arxiv_meta = fetch_arxiv_papers_batch(arxiv_ids)
        except (requests.RequestException, ET.ParseError):
            arxiv_meta = {}
        for entry in refs:
            aid = entry.pop("arxiv_id", None)
            if aid and aid in arxiv_meta:
                meta = arxiv_meta[aid]
                entry["title"] = meta["title"]
                entry["url"] = meta["url"]
                entry["published"] = meta["published"]
                entry["authors"] = meta["authors"]
                entry["summary"] = meta["summary"]

    return refs


def extract_paper_id(link: str) -> str:
    """Extract paper ID from an arXiv link."""
    if "/abs/" in link:
        return link.split("/abs/")[-1].rstrip("/")
    if "/pdf/" in link:
        return link.split("/pdf/")[-1].replace(".pdf", "")
    return link


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python arxiv_scraper.py <arxiv_link>", file=sys.stderr)
        return 1

    paper_id = extract_paper_id(sys.argv[1])

    try:
        result = fetch_arxiv_paper(paper_id)
    except (requests.RequestException, ET.ParseError) as exc:
        print(json.dumps({"error": f"Failed to fetch paper: {exc}"}), file=sys.stderr)
        return 1

    if not result:
        print(json.dumps({"error": f"No paper found for ID '{paper_id}'"}), file=sys.stderr)
        return 1

    try:
        result["references"] = fetch_references(paper_id)
    except requests.RequestException as exc:
        result["references"] = []
        result["references_error"] = f"Failed to fetch references: {exc}"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
