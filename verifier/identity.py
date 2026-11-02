"""Paper checks and the same identity rule the tool uses to drop duplicates."""

import re

PMID = re.compile(r"^[1-9][0-9]{0,8}$")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
MAX_PAPERS = 20
TITLE_MAX = 500
TITLE_FORBIDDEN = "\"[]\\"
KINDS = ("pmid", "doi", "title")


def normalize_title(text):
    collapsed = " ".join(text.split()).removesuffix(".")
    return collapsed.casefold()


def paper_key(paper):
    kind = paper.kind.value
    if kind == "pmid":
        return (kind, paper.value)
    if kind == "doi":
        return (kind, paper.value.casefold())
    return (kind, normalize_title(paper.value))


def input_problem(value):
    """A (kind, message) pair, or None when every paper can be resolved."""
    if len(value.papers) > MAX_PAPERS:
        return ("malformed", f"papers has more than {MAX_PAPERS} items")
    for paper in value.papers:
        problem = paper_problem(paper)
        if problem:
            return problem
    return None


def output_problem(output):
    """A (kind, message) pair, or None when the subset list is well formed."""
    if len(output.available) > MAX_PAPERS:
        return ("malformed", f"available has more than {MAX_PAPERS} papers")
    seen = []
    for paper in output.available:
        problem = paper_problem(paper)
        if problem:
            return problem
        key = paper_key(paper)
        if key in seen:
            return ("wrong", "available repeats a paper")
        seen.append(key)
    return None


def paper_problem(paper):
    kind = paper.kind.value
    raw = paper.value
    if kind not in KINDS:
        return ("malformed", "kind is not pmid, doi, or title")
    if raw.strip() == "":
        return ("missing", f"{kind} is empty")
    if kind == "pmid" and PMID.fullmatch(raw) is None:
        return ("malformed", "pmid is not a PubMed id")
    if kind == "doi" and (DOI.fullmatch(raw) is None or '"' in raw):
        return ("malformed", "doi is not a DOI")
    if kind == "title":
        if len(raw.strip()) > TITLE_MAX:
            return ("malformed", f"title is longer than {TITLE_MAX} characters")
        if any(ord(char) < 32 or ord(char) == 127 for char in raw):
            return ("malformed", "title contains a control character")
        if any(char in raw for char in TITLE_FORBIDDEN):
            return ("malformed", "title contains a character the title search cannot quote")
    return None


def same_papers(left, right):
    if len(left) != len(right):
        return False
    for found, expected in zip(left, right):
        if found.kind != expected.kind or found.value != expected.value:
            return False
    return True


def subset_from_rows(papers, rows):
    chosen = []
    seen = set()
    for paper, row in zip(papers, rows):
        if not row["available"]:
            continue
        key = paper_key(paper)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(paper)
    return chosen
