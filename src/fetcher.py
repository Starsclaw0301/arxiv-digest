"""
Step 1: Fetch today's cs.RO papers from arXiv RSS feed.
Enriches with arXiv Search API metadata.
Writes to data/papers.json.
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

RSS_URL = "https://rss.arxiv.org/rss/cs.RO"
SEARCH_API = "https://export.arxiv.org/api/query"
DATA_DIR = Path(__file__).parent.parent / "data"


def fetch_rss() -> list[dict]:
    """Fetch arXiv cs.RO RSS and return list of papers with basic metadata."""
    resp = requests.get(RSS_URL, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    ns = {
        "arxiv": "http://arxiv.org/schemas/atom",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    papers = []
    channel = root.find("channel")
    if channel is None:
        return papers

    for item in channel.findall("item"):
        link = item.findtext("link", "").strip()
        title = item.findtext("title", "").strip()
        description = item.findtext("description", "").strip()

        # Extract arxiv_id from link
        arxiv_id = ""
        if "/abs/" in link:
            arxiv_id = link.split("/abs/")[-1].strip()

        # Determine announce type from description
        announce_type = "new"
        if "cross-list" in description.lower():
            announce_type = "cross"
        elif "replaced" in description.lower():
            announce_type = "replace"

        # Skip replaced papers
        if announce_type == "replace":
            continue

        papers.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "link": link,
            "announce_type": announce_type,
            "abstract": "",  # Will be enriched
            "authors": [],
            "venue": "",
            "project_page": "",
        })

    return papers


def enrich_with_search_api(papers: list[dict]) -> list[dict]:
    """Enrich papers with abstract and author info from arXiv Search API."""
    if not papers:
        return papers

    # Batch in groups of 50
    batch_size = 50
    enriched = []

    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]
        ids = [p["arxiv_id"] for p in batch if p["arxiv_id"]]

        if not ids:
            enriched.extend(batch)
            continue

        id_list = ",".join(ids)
        params = {
            "id_list": id_list,
            "max_results": len(ids),
        }

        try:
            resp = requests.get(SEARCH_API, params=params, timeout=30)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            atom_ns = "http://www.w3.org/2005/Atom"

            entries = {
                entry.find(f"{{{atom_ns}}}id").text.split("/abs/")[-1].split("v")[0]: entry
                for entry in root.findall(f"{{{atom_ns}}}entry")
                if entry.find(f"{{{atom_ns}}}id") is not None
            }

            for paper in batch:
                pid = paper["arxiv_id"].split("v")[0]
                entry = entries.get(pid)
                if entry:
                    abstract_el = entry.find(f"{{{atom_ns}}}summary")
                    if abstract_el is not None:
                        paper["abstract"] = abstract_el.text.strip().replace("\n", " ")

                    authors = []
                    for author in entry.findall(f"{{{atom_ns}}}author"):
                        name_el = author.find(f"{{{atom_ns}}}name")
                        if name_el is not None:
                            authors.append(name_el.text.strip())
                    paper["authors"] = authors[:5]  # Keep first 5

                enriched.append(paper)

            time.sleep(0.5)  # Be polite to arXiv API

        except Exception as e:
            print(f"Warning: Search API enrichment failed for batch: {e}")
            enriched.extend(batch)

    return enriched


def main():
    DATA_DIR.mkdir(exist_ok=True)
    print("Fetching arXiv cs.RO RSS feed...")
    papers = fetch_rss()
    print(f"Found {len(papers)} new/cross papers")

    print("Enriching with arXiv Search API...")
    papers = enrich_with_search_api(papers)

    output_path = DATA_DIR / "papers.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(papers)} papers to {output_path}")
    return papers


if __name__ == "__main__":
    main()
