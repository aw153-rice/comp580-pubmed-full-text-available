"""Resolve PMIDs, DOIs, and titles, then keep PubMed's free full text subset."""

from __future__ import annotations

import os
import re

from contract import FullTextInput, FullTextOutput, PaperKind
from plugin.client import ESEARCH_URL, ESUMMARY_URL, TOOL_NAME

MAX_PAPERS = 20
TITLE_MAX = 500
PMID = re.compile(r"^[1-9][0-9]{0,8}$")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
TITLE_FORBIDDEN = "\"[]\\"


def normalize_title(text: str) -> str:
    collapsed = " ".join(text.split()).removesuffix(".")
    return collapsed.casefold()


def identity(paper) -> tuple[str, str]:
    kind = paper.kind.value
    if kind == PaperKind.PMID.value:
        return (kind, paper.value)
    if kind == PaperKind.DOI.value:
        return (kind, paper.value.casefold())
    return (kind, normalize_title(paper.value))


def select_papers(given: FullTextInput, client) -> tuple[FullTextOutput, list[dict]]:
    check_papers(given.papers)
    resolved: dict[tuple[str, str], str | None] = {}
    for paper in given.papers:
        key = identity(paper)
        if key not in resolved:
            resolved[key] = resolve_paper(client, paper)
    free = free_pmids(client, [pmid for pmid in resolved.values() if pmid is not None])
    rows = []
    available = []
    seen: set[tuple[str, str]] = set()
    for paper in given.papers:
        key = identity(paper)
        pmid = resolved[key]
        is_free = pmid is not None and pmid in free
        rows.append({"kind": paper.kind.value, "value": paper.value, "pmid": pmid, "available": is_free})
        if is_free and key not in seen:
            seen.add(key)
            available.append(paper)
    return FullTextOutput(available=available), rows


def check_papers(papers) -> None:
    if len(papers) > MAX_PAPERS:
        raise ValueError(f"papers has more than {MAX_PAPERS} items")
    for paper in papers:
        problem = paper_problem(paper)
        if problem:
            raise ValueError(problem)


def paper_problem(paper) -> str | None:
    kind = paper.kind.value
    raw = paper.value
    if raw.strip() == "":
        return f"{kind} is empty"
    if kind == PaperKind.PMID.value:
        if PMID.fullmatch(raw) is None:
            return "pmid is not a PubMed id"
        return None
    if kind == PaperKind.DOI.value:
        if DOI.fullmatch(raw) is None or '"' in raw:
            return "doi is not a DOI"
        return None
    if len(raw.strip()) > TITLE_MAX:
        return f"title is longer than {TITLE_MAX} characters"
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        return "title contains a control character"
    if any(char in raw for char in TITLE_FORBIDDEN):
        return "title contains a character the title search cannot quote"
    return None


def resolve_paper(client, paper) -> str | None:
    if paper.kind is PaperKind.PMID:
        count, ids = esearch(client, f"{paper.value}[uid]", 1)
        if count == 0:
            return None
        if count != 1 or ids != [paper.value]:
            raise RuntimeError(f"ESearch returned an unexpected record for pmid {paper.value}")
        return paper.value
    if paper.kind is PaperKind.DOI:
        count, ids = esearch(client, f'"{paper.value}"[doi]', 2)
        if count == 0:
            return None
        if count != 1 or len(ids) != 1:
            raise RuntimeError(f"DOI matches more than one PubMed record: {paper.value}")
        return ids[0]
    return resolve_title(client, paper.value)


def resolve_title(client, value: str) -> str | None:
    query = " ".join(value.split())
    count, ids = esearch(client, f'"{query}"[Title]', MAX_PAPERS)
    if count == 0:
        return None
    if count > MAX_PAPERS:
        raise RuntimeError(f"title search returned more than {MAX_PAPERS} hits")
    titles = fetch_titles(client, ids)
    wanted = normalize_title(value)
    found = [pmid for pmid in ids if normalize_title(titles[pmid]) == wanted]
    if not found:
        return None
    if len(found) > 1:
        raise RuntimeError(f"title matches more than one PubMed record: {value}")
    return found[0]


def free_pmids(client, pmids: list[str]) -> set[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for pmid in pmids:
        if pmid not in seen:
            seen.add(pmid)
            unique.append(pmid)
    if not unique:
        return set()
    term = "(" + " OR ".join(f"{pmid}[uid]" for pmid in unique) + ") AND free full text[sb]"
    count, ids = esearch(client, term, len(unique))
    if count > len(unique) or len(ids) != count:
        raise RuntimeError("free full text search returned more hits than the PMIDs sent")
    extra = [pmid for pmid in ids if pmid not in seen]
    if extra:
        raise RuntimeError(f"free full text search returned an unexpected pmid {extra[0]}")
    return set(ids)


def esearch(client, term: str, retmax: int) -> tuple[int, list[str]]:
    body = client.get_json(
        ESEARCH_URL,
        ncbi_params(
            {
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": str(retmax),
                "retstart": "0",
            }
        ),
    )
    if body.get("error"):
        raise RuntimeError(f"ESearch error: {body['error']}")
    result = body.get("esearchresult")
    if not isinstance(result, dict):
        raise TypeError("ESearch returned no esearchresult")
    if result.get("ERROR") or result.get("errorlist"):
        raise RuntimeError(f"ESearch error: {result.get('ERROR') or result.get('errorlist')}")
    try:
        count = int(result.get("count"))
    except (TypeError, ValueError) as error:
        raise RuntimeError("ESearch returned no count") from error
    idlist = result.get("idlist")
    if not isinstance(idlist, list):
        raise TypeError("ESearch returned no id list")
    if count > retmax:
        return count, []
    if len(idlist) != count:
        raise RuntimeError("ESearch id list does not cover every hit")
    pmids = []
    seen: set[str] = set()
    for raw in idlist:
        pmid = as_pmid(raw)
        if pmid in seen:
            raise RuntimeError(f"ESearch repeated pmid {pmid}")
        seen.add(pmid)
        pmids.append(pmid)
    return count, pmids


def fetch_titles(client, pmids: list[str]) -> dict[str, str]:
    body = client.get_json(ESUMMARY_URL, ncbi_params({"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}))
    if body.get("error"):
        raise RuntimeError(f"ESummary error: {body['error']}")
    result = body.get("result")
    if not isinstance(result, dict):
        raise TypeError("ESummary returned no result")
    uids = result.get("uids")
    if not isinstance(uids, list):
        raise TypeError("ESummary returned no uids")
    titles: dict[str, str] = {}
    for raw in uids:
        pmid = as_pmid(raw)
        record = result.get(pmid)
        if not isinstance(record, dict):
            raise TypeError("ESummary returned a record that is not an object")
        if record.get("error"):
            raise RuntimeError(f"ESummary error: {record['error']}")
        title = record.get("title")
        if not isinstance(title, str) or title.strip() == "":
            raise TypeError("ESummary returned a record without a title")
        if pmid in titles:
            raise RuntimeError(f"ESummary repeated pmid {pmid}")
        titles[pmid] = title
    if set(titles) != set(pmids):
        raise RuntimeError("ESummary did not return every hit")
    return titles


def ncbi_params(extra: dict[str, str]) -> dict[str, str]:
    params = {"tool": TOOL_NAME, **extra}
    email = os.environ.get("NCBI_EMAIL", "").strip()
    api_key = os.environ.get("NCBI_API_KEY", "").strip()
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    return params


def as_pmid(raw) -> str:
    if isinstance(raw, bool) or not isinstance(raw, int | str):
        raise TypeError(f"invalid pmid: {raw!r}")
    text = str(raw).strip()
    if PMID.fullmatch(text) is None:
        raise RuntimeError(f"invalid pmid: {raw!r}")
    return text
