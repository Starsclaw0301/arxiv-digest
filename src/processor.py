"""
Step 3: Process relevance verdicts, detect venue, find project pages,
generate markdown digest, and sync to Zotero.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
DIGEST_DIR = Path(__file__).parent.parent / "digests"
SECRET_DIR = Path(__file__).parent.parent / ".secret"

ZOTERO_ENV = SECRET_DIR / "zotero.env"


def load_env(path: Path):
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()


def detect_venue(paper: dict) -> str:
    """Detect conference/journal from abstract comments or title."""
    abstract = paper.get("abstract", "")
    title = paper.get("title", "")
    text = (abstract + " " + title).upper()

    venues = [
        ("ICRA", "ICRA"), ("IROS", "IROS"), ("CoRL", "CoRL"),
        ("RSS", "RSS"), ("NeurIPS", "NEURIPS"), ("ICML", "ICML"),
        ("ICLR", "ICLR"), ("CVPR", "CVPR"), ("ICCV", "ICCV"),
        ("ECCV", "ECCV"), ("RA-L", "RA-L"), ("T-RO", "T-RO"),
        ("IJRR", "IJRR"), ("Science Robotics", "SCIENCE ROBOTICS"),
    ]
    for display, keyword in venues:
        if keyword in text:
            return display
    return "arXiv"


def find_project_page(paper: dict) -> str:
    """Extract project page URL from abstract."""
    abstract = paper.get("abstract", "")
    patterns = [
        r"https?://[^\s]+\.github\.io[^\s]*",
        r"https?://github\.com/[^\s]+",
        r"project page[:\s]+(?:at\s+)?(https?://[^\s]+)",
        r"code[:\s]+(?:at\s+)?(https?://[^\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, abstract, re.IGNORECASE)
        if match:
            url = match.group(1) if match.lastindex else match.group(0)
            return url.rstrip(".,)")
    return ""


def add_to_zotero(paper: dict, venue: str) -> bool:
    """Add paper to Zotero personal library with PDF."""
    load_env(ZOTERO_ENV)
    api_key = os.environ.get("ZOTERO_API_KEY", "")
    user_id = os.environ.get("ZOTERO_USER_ID", "")

    if not api_key or not user_id:
        return False

    base_url = f"https://api.zotero.org/users/{user_id}"
    headers = {
        "Zotero-API-Key": api_key,
        "Content-Type": "application/json",
    }

    arxiv_id = paper.get("arxiv_id", "")

    # Check dedup
    try:
        resp = requests.get(
            f"{base_url}/items",
            params={"q": arxiv_id, "limit": 5},
            headers=headers,
            timeout=15,
        )
        if resp.ok:
            for item in resp.json():
                url = item.get("data", {}).get("url", "")
                if arxiv_id in url:
                    return True  # Already exists
    except Exception:
        pass

    # Determine item type
    if venue in ("arXiv",):
        item_type = "preprint"
    elif venue in ("RA-L", "T-RO", "IJRR", "Science Robotics"):
        item_type = "journalArticle"
    else:
        item_type = "conferencePaper"

    item_data = {
        "itemType": item_type,
        "title": paper.get("title", ""),
        "abstractNote": paper.get("abstract", ""),
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "creators": [
            {"creatorType": "author", "name": a}
            for a in paper.get("authors", [])
        ],
    }
    if venue != "arXiv":
        if item_type == "conferencePaper":
            item_data["conferenceName"] = venue
        else:
            item_data["publicationTitle"] = venue

    try:
        resp = requests.post(
            f"{base_url}/items",
            headers=headers,
            json=[item_data],
            timeout=15,
        )
        if not resp.ok:
            return False

        item_key = resp.json().get("successful", {}).get("0", {}).get("key", "")
        if not item_key:
            return False

        # Attach PDF
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        pdf_resp = requests.get(pdf_url, timeout=30)
        if pdf_resp.ok:
            attach_headers = {
                "Zotero-API-Key": api_key,
                "Content-Type": "application/pdf",
            }
            requests.post(
                f"{base_url}/items/{item_key}/file",
                headers=attach_headers,
                data=pdf_resp.content,
                timeout=30,
            )
        return True
    except Exception:
        return False


def generate_digest(papers: list[dict], relevant: list[dict], date_str: str) -> str:
    """Generate markdown digest."""
    # Group by theme
    themes = {
        "vla": {"emoji": "🤖", "label": "VLA / 模仿学习"},
        "dexterous": {"emoji": "🖐️", "label": "灵巧手 / 触觉感知"},
        "data": {"emoji": "📦", "label": "数据采集 / 遥操作"},
        "humanoid": {"emoji": "🦾", "label": "人形机器人 / 全身控制"},
        "other": {"emoji": "📌", "label": "其他"},
    }

    grouped: dict[str, list] = {k: [] for k in themes}
    must_read = []

    for r in relevant:
        theme = r.get("theme", "other")
        if theme not in grouped:
            theme = "other"
        grouped[theme].append(r)
        if r.get("stars", 0) >= 3:
            must_read.append(r)

    lines = [f"# cs.RO 日报 · {date_str}\n"]

    for theme_key, meta in themes.items():
        items = grouped[theme_key]
        if not items:
            continue
        lines.append(f"## {meta['emoji']} {meta['label']}\n")
        for r in items:
            stars = "⭐" * r.get("stars", 1)
            title = r.get("title", "")
            arxiv_id = r.get("arxiv_id", "")
            reason = r.get("reason", "")
            venue = r.get("venue", "arXiv")
            project = r.get("project_page", "")

            venue_tag = f" `{venue}`" if venue != "arXiv" else ""
            project_tag = f" · [项目页]({project})" if project else ""

            lines.append(f"**{title}**{venue_tag} {stars}")
            lines.append(reason)
            lines.append(f"https://arxiv.org/abs/{arxiv_id}{project_tag}\n")

    if must_read:
        lines.append("---\n**今日必读** ⭐⭐⭐")
        for r in must_read:
            lines.append(f"- {r.get('title', '')}")

    return "\n".join(lines)


def main(dry_run: bool = False):
    load_env(ZOTERO_ENV)
    DIGEST_DIR.mkdir(exist_ok=True)

    papers_path = DATA_DIR / "papers.json"
    relevance_path = DATA_DIR / "relevance.json"

    with open(papers_path, encoding="utf-8") as f:
        papers = json.load(f)

    with open(relevance_path, encoding="utf-8") as f:
        relevance = json.load(f)

    paper_map = {p["arxiv_id"]: p for p in papers}
    relevant = [r for r in relevance if r.get("is_relevant")]

    # Enrich relevant papers
    for r in relevant:
        paper = paper_map.get(r["arxiv_id"], {})
        r["title"] = paper.get("title", r["arxiv_id"])
        r["abstract"] = paper.get("abstract", "")
        r["authors"] = paper.get("authors", [])
        r["venue"] = detect_venue(paper)
        r["project_page"] = find_project_page(paper)

    date_str = datetime.now().strftime("%Y-%m-%d")
    digest = generate_digest(papers, relevant, date_str)

    digest_path = DIGEST_DIR / f"{date_str}.md"
    digest_path.write_text(digest, encoding="utf-8")
    print(f"Digest written to {digest_path}")

    if not dry_run:
        print(f"Syncing {len(relevant)} papers to Zotero...")
        for r in relevant:
            success = add_to_zotero(r, r["venue"])
            status = "✅" if success else "⚠️"
            print(f"  {status} {r['arxiv_id']}: {r['title'][:50]}")
            time.sleep(0.3)

    print("\n" + digest)
    return digest


if __name__ == "__main__":
    import sys
    main(dry_run="--dry-run" in sys.argv)
