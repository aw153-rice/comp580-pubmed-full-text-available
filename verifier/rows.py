"""Read availability.json. The stored subset is checked against these rows."""

import json
from pathlib import Path

from .identity import PMID, paper_key

FILE_NAME = "availability.json"


def load_rows(workspace, papers):
    """Return ("ok", rows), or ("missing"|"malformed", message)."""
    path = Path(workspace) / FILE_NAME
    if not path.is_file():
        return ("missing", "availability.json is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ("malformed", "availability.json is not JSON")
    if type(data) is not dict or type(data.get("papers")) is not list:
        return ("malformed", "availability.json has no papers list")
    rows = data["papers"]
    if len(rows) != len(papers):
        return ("malformed", "availability.json row count does not match the input")
    parsed = []
    for paper, row in zip(papers, rows):
        problem = row_problem(paper, row)
        if problem:
            return problem
        parsed.append({"kind": row["kind"], "value": row["value"], "pmid": row["pmid"], "available": row["available"]})
    problem = duplicate_problem(papers, parsed)
    if problem:
        return ("malformed", problem)
    return ("ok", parsed)


def row_problem(paper, row):
    if type(row) is not dict:
        return ("malformed", "availability.json has a paper that is not an object")
    if row.get("kind") != paper.kind.value or row.get("value") != paper.value:
        return ("malformed", "availability.json row does not match the input")
    pmid = row.get("pmid")
    available = row.get("available")
    if pmid is not None and (type(pmid) is not str or PMID.fullmatch(pmid) is None):
        return ("malformed", "availability.json has an invalid pmid")
    if type(available) is not bool:
        return ("malformed", "availability.json has an invalid available flag")
    if available and pmid is None:
        return ("malformed", "availability.json marks a paper available without a pmid")
    return None


def duplicate_problem(papers, rows):
    seen = {}
    for paper, row in zip(papers, rows):
        key = paper_key(paper)
        marker = (row["available"], row["pmid"])
        if key in seen and seen[key] != marker:
            return "availability.json disagrees on a repeated paper"
        seen[key] = marker
    return None
