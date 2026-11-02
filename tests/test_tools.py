"""Tool tests. The HTTP client is a fake, so nothing here opens a socket."""

import json
import re
from pathlib import Path

import httpx
import pytest
from slimconfig import build_output

import verifier
from contract import FullTextInput
from plugin.client import ESEARCH_URL, ESUMMARY_URL, HttpxClient, set_client
from plugin.full_text import AVAILABILITY_FILE, full_text_available
from plugin.pin import pin_full_text
from plugin.select import normalize_title

SAMPLE = [
    {"kind": "pmid", "value": "100"},
    {"kind": "doi", "value": "10.1000/xyz"},
    {"kind": "title", "value": "A free paper"},
    {"kind": "pmid", "value": "999"},
]
EXISTS = {"100", "200", "300", "400", "401", "402", "1", "123456789"}
FREE = {"100", "300", "1", "123456789"}
DOIS = {"10.1000/xyz": ["200"], "10.1000/many": ["200", "201"], "10.1000/same": ["100"]}
SUMMARIES = {
    "300": "A free paper.",
    "400": "Almost paper extra",
    "401": "Shared title",
    "402": "Shared title",
}
TITLE_HITS = {
    "a free paper": ["300"],
    "almost paper": ["400"],
    "shared title": ["401", "402"],
    "no such paper": [],
}
UID = re.compile(r"(\d+)\[uid\]")


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get_json(self, url, params):
        self.calls.append((url, dict(params)))
        return self.handler(url, params)


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    holder = {}

    def install(handler):
        client = FakeClient(handler)
        holder["client"] = client
        set_client(client)
        return client

    yield install
    set_client(None)


def given(papers=None):
    return build_output({"papers": SAMPLE if papers is None else papers}, FullTextInput)


def esearch(pmids, count=None):
    total = len(pmids) if count is None else count
    return {"esearchresult": {"count": str(total), "idlist": list(pmids)}}


def esummary(titles):
    result = {"uids": list(titles)}
    for pmid, title in titles.items():
        result[pmid] = {"uid": pmid, "title": title}
    return {"result": result}


def quoted(term, field):
    suffix = f'"[{field}]'
    if not (term.startswith('"') and term.endswith(suffix)):
        raise AssertionError(term)
    return term[1 : -len(suffix)]


def catalog(url, params):
    if url == ESUMMARY_URL:
        ids = [part for part in params["id"].split(",") if part]
        return esummary({pmid: SUMMARIES[pmid] for pmid in ids})
    term = params["term"]
    if "free full text[sb]" in term:
        return esearch([pmid for pmid in UID.findall(term) if pmid in FREE])
    if term.endswith("[uid]") and " OR " not in term:
        pmid = term[: -len("[uid]")]
        return esearch([pmid] if pmid in EXISTS else [])
    if term.endswith("[doi]"):
        return esearch(DOIS.get(quoted(term, "doi"), []))
    if term.endswith("[Title]"):
        key = normalize_title(quoted(term, "Title"))
        if key == "too many hits":
            return esearch(["300"], count=21)
        if key not in TITLE_HITS:
            raise AssertionError(term)
        return esearch(TITLE_HITS[key])
    raise AssertionError((url, term))


def values(output):
    return [(paper.kind.value, paper.value) for paper in output.available]


def test_returns_the_free_subset_and_writes_rows(fake, tmp_path: Path):
    client = fake(catalog)
    output = full_text_available(given(), tmp_path)
    assert values(output) == [("pmid", "100"), ("title", "A free paper")]
    saved = json.loads((tmp_path / AVAILABILITY_FILE).read_text(encoding="utf-8"))
    assert saved["papers"] == [
        {"kind": "pmid", "value": "100", "pmid": "100", "available": True},
        {"kind": "doi", "value": "10.1000/xyz", "pmid": "200", "available": False},
        {"kind": "title", "value": "A free paper", "pmid": "300", "available": True},
        {"kind": "pmid", "value": "999", "pmid": None, "available": False},
    ]
    assert [call[0] for call in client.calls] == [
        ESEARCH_URL,
        ESEARCH_URL,
        ESEARCH_URL,
        ESUMMARY_URL,
        ESEARCH_URL,
        ESEARCH_URL,
    ]
    assert client.calls[0][1]["term"] == "100[uid]"
    assert client.calls[0][1]["retmax"] == "1"
    assert client.calls[0][1]["tool"] == "pubmed-full-text-available"
    assert client.calls[1][1]["term"] == '"10.1000/xyz"[doi]'
    assert client.calls[2][1]["term"] == '"A free paper"[Title]'
    assert client.calls[3][1]["id"] == "300"
    assert client.calls[4][1]["term"] == "999[uid]"
    assert client.calls[5][1]["term"] == "(100[uid] OR 200[uid] OR 300[uid]) AND free full text[sb]"
    verdict = verifier.verify_task("pubmed-full-text-available", given(), output, output, str(tmp_path))
    assert verdict["valid"] is True


def test_pin_returns_the_same_subset_and_writes_nothing(fake, tmp_path: Path):
    fake(catalog)
    output = pin_full_text(given(), tmp_path)
    assert values(output) == [("pmid", "100"), ("title", "A free paper")]
    assert list(tmp_path.iterdir()) == []


def test_empty_input_skips_the_network(fake, tmp_path: Path):
    client = fake(catalog)
    output = full_text_available(given([]), tmp_path)
    assert output.available == []
    assert client.calls == []
    saved = json.loads((tmp_path / AVAILABILITY_FILE).read_text(encoding="utf-8"))
    assert saved == {"papers": []}


def test_unresolved_papers_are_left_out(fake, tmp_path: Path):
    client = fake(catalog)
    papers = [
        {"kind": "pmid", "value": "999"},
        {"kind": "doi", "value": "10.1000/missing"},
        {"kind": "title", "value": "No such paper"},
    ]
    output = full_text_available(given(papers), tmp_path)
    assert output.available == []
    assert all("free full text[sb]" not in call[1]["term"] for call in client.calls)


def test_a_near_title_is_not_the_record(fake, tmp_path: Path):
    fake(catalog)
    output = full_text_available(given([{"kind": "title", "value": "Almost paper"}]), tmp_path)
    assert output.available == []
    saved = json.loads((tmp_path / AVAILABILITY_FILE).read_text(encoding="utf-8"))
    assert saved["papers"] == [{"kind": "title", "value": "Almost paper", "pmid": None, "available": False}]


def test_collapsed_title_keeps_the_original_value(fake, tmp_path: Path):
    client = fake(catalog)
    output = full_text_available(given([{"kind": "title", "value": "A   free paper"}]), tmp_path)
    assert values(output) == [("title", "A   free paper")]
    assert client.calls[0][1]["term"] == '"A free paper"[Title]'


def test_duplicate_pmid_is_kept_once(fake, tmp_path: Path):
    client = fake(catalog)
    papers = [{"kind": "pmid", "value": "100"}, {"kind": "pmid", "value": "100"}]
    output = full_text_available(given(papers), tmp_path)
    assert values(output) == [("pmid", "100")]
    assert client.calls[-1][1]["term"] == "(100[uid]) AND free full text[sb]"
    saved = json.loads((tmp_path / AVAILABILITY_FILE).read_text(encoding="utf-8"))
    assert [row["available"] for row in saved["papers"]] == [True, True]


def test_title_case_and_a_trailing_period_are_one_paper(fake, tmp_path: Path):
    client = fake(catalog)
    papers = [
        {"kind": "title", "value": "A free paper"},
        {"kind": "title", "value": "a free paper."},
    ]
    output = full_text_available(given(papers), tmp_path)
    assert values(output) == [("title", "A free paper")]
    assert [call[0] for call in client.calls].count(ESEARCH_URL) == 2


def test_different_identifiers_for_one_pmid_both_remain(fake, tmp_path: Path):
    fake(catalog)
    papers = [{"kind": "pmid", "value": "100"}, {"kind": "doi", "value": "10.1000/same"}]
    output = full_text_available(given(papers), tmp_path)
    assert values(output) == [("pmid", "100"), ("doi", "10.1000/same")]


def test_short_and_long_pmids_are_accepted(fake, tmp_path: Path):
    fake(catalog)
    papers = [{"kind": "pmid", "value": "1"}, {"kind": "pmid", "value": "123456789"}]
    output = full_text_available(given(papers), tmp_path)
    assert values(output) == [("pmid", "1"), ("pmid", "123456789")]


def test_ambiguous_doi_raises_and_writes_nothing(fake, tmp_path: Path):
    fake(catalog)
    with pytest.raises(RuntimeError, match="more than one"):
        full_text_available(given([{"kind": "doi", "value": "10.1000/many"}]), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_ambiguous_title_raises_and_writes_nothing(fake, tmp_path: Path):
    fake(catalog)
    with pytest.raises(RuntimeError, match="more than one"):
        full_text_available(given([{"kind": "title", "value": "Shared title"}]), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_title_page_above_20_raises(fake, tmp_path: Path):
    fake(catalog)
    with pytest.raises(RuntimeError, match="more than 20"):
        full_text_available(given([{"kind": "title", "value": "Too many hits"}]), tmp_path)


@pytest.mark.parametrize(
    ("papers", "match"),
    [
        ([{"kind": "pmid", "value": "   "}], "pmid is empty"),
        ([{"kind": "pmid", "value": "0100"}], "pmid is not a PubMed id"),
        ([{"kind": "doi", "value": "10.1/x"}], "doi is not a DOI"),
        ([{"kind": "doi", "value": '10.1000/ab"c'}], "doi is not a DOI"),
        ([{"kind": "title", "value": "Bad [title]"}], "cannot quote"),
        ([{"kind": "title", "value": "bad\ntitle"}], "control character"),
        ([{"kind": "pmid", "value": str(number)} for number in range(1, 22)], "more than 20"),
    ],
)
def test_rejects_a_bad_paper_before_calling(fake, tmp_path: Path, papers, match):
    client = fake(catalog)
    with pytest.raises(ValueError, match=match):
        full_text_available(given(papers), tmp_path)
    assert client.calls == []


def test_sends_optional_credentials(fake, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("NCBI_EMAIL", "reader@example.com")
    monkeypatch.setenv("NCBI_API_KEY", "secret")
    client = fake(catalog)
    full_text_available(given([{"kind": "pmid", "value": "100"}]), tmp_path)
    assert client.calls[0][1]["email"] == "reader@example.com"
    assert client.calls[0][1]["api_key"] == "secret"


def test_raises_when_the_id_list_is_short(fake, tmp_path: Path):
    fake(lambda url, params: {"esearchresult": {"count": "1", "idlist": []}})
    with pytest.raises(RuntimeError, match="does not cover"):
        full_text_available(given([{"kind": "pmid", "value": "100"}]), tmp_path)


def test_raises_on_a_repeated_pmid(fake, tmp_path: Path):
    fake(lambda url, params: {"esearchresult": {"count": "2", "idlist": ["100", "100"]}})
    with pytest.raises(RuntimeError, match="repeated"):
        full_text_available(given([{"kind": "doi", "value": "10.1000/xyz"}]), tmp_path)


def test_raises_on_an_esearch_error(fake, tmp_path: Path):
    fake(lambda url, params: {"esearchresult": {"ERROR": "search failed"}})
    with pytest.raises(RuntimeError, match="search failed"):
        full_text_available(given([{"kind": "pmid", "value": "100"}]), tmp_path)


def test_raises_when_the_filter_returns_an_unexpected_pmid(fake, tmp_path: Path):
    def handler(url, params):
        if "free full text[sb]" in params["term"]:
            return esearch(["888"])
        return esearch(["100"])

    fake(handler)
    with pytest.raises(RuntimeError, match="unexpected pmid 888"):
        full_text_available(given([{"kind": "pmid", "value": "100"}]), tmp_path)


def test_raises_when_a_summary_has_no_title(fake, tmp_path: Path):
    def handler(url, params):
        if url == ESUMMARY_URL:
            return {"result": {"uids": ["300"], "300": {"uid": "300"}}}
        if params["term"].endswith("[Title]"):
            return esearch(["300"])
        raise AssertionError(params["term"])

    fake(handler)
    with pytest.raises(TypeError, match="without a title"):
        full_text_available(given([{"kind": "title", "value": "A free paper"}]), tmp_path)


def test_http_status_non_json_and_non_object_raise():
    def status(_request):
        return httpx.Response(503, text="no")

    client = HttpxClient(transport=httpx.MockTransport(status), pause=0)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        client.get_json(ESEARCH_URL, {})

    def text(_request):
        return httpx.Response(200, text="not-json")

    client = HttpxClient(transport=httpx.MockTransport(text), pause=0)
    with pytest.raises(RuntimeError, match="not JSON"):
        client.get_json(ESEARCH_URL, {})

    def listed(_request):
        return httpx.Response(200, json=["not", "an", "object"])

    client = HttpxClient(transport=httpx.MockTransport(listed), pause=0)
    with pytest.raises(TypeError, match="not a JSON object"):
        client.get_json(ESEARCH_URL, {})
