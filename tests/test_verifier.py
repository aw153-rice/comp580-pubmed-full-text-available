"""Verifier cases: correct, wrong, missing, malformed, and boundary."""

import json
from pathlib import Path

from slimconfig import build_output

import verifier
from contract import FullTextInput, FullTextOutput

SAMPLE = [
    {"kind": "pmid", "value": "100"},
    {"kind": "doi", "value": "10.1000/xyz"},
    {"kind": "title", "value": "A free paper"},
    {"kind": "pmid", "value": "999"},
]
KEPT = [SAMPLE[0], SAMPLE[2]]
ROWS = [
    {"kind": "pmid", "value": "100", "pmid": "100", "available": True},
    {"kind": "doi", "value": "10.1000/xyz", "pmid": "200", "available": False},
    {"kind": "title", "value": "A free paper", "pmid": "300", "available": True},
    {"kind": "pmid", "value": "999", "pmid": None, "available": False},
]


def given(papers=None):
    return build_output({"papers": SAMPLE if papers is None else papers}, FullTextInput)


def made(papers):
    return build_output({"available": papers}, FullTextOutput)


def write_rows(workspace: Path, rows) -> None:
    (workspace / "availability.json").write_text(json.dumps({"papers": rows}), encoding="utf-8")


def test_verify_input_accepts_the_sample():
    assert verifier.verify_input("full_text_available", given())["valid"] is True
    assert verifier.verify_input("pin_full_text", given())["valid"] is True


def test_verify_input_rejects_a_blank_value():
    verdict = verifier.verify_input("full_text_available", given([{"kind": "pmid", "value": "   "}]))
    assert verdict["valid"] is False
    assert "empty" in verdict["message"]


def test_verify_input_rejects_malformed_papers():
    leading = verifier.verify_input("full_text_available", given([{"kind": "pmid", "value": "0100"}]))
    assert leading["valid"] is False
    assert "pmid" in leading["message"]
    short_doi = verifier.verify_input("pin_full_text", given([{"kind": "doi", "value": "10.1/x"}]))
    assert short_doi["valid"] is False
    assert "doi" in short_doi["message"]
    bracket = verifier.verify_input("full_text_available", given([{"kind": "title", "value": "Bad [title]"}]))
    assert bracket["valid"] is False
    assert "quote" in bracket["message"]
    too_many = [{"kind": "pmid", "value": str(number)} for number in range(1, 22)]
    oversized = verifier.verify_input("full_text_available", given(too_many))
    assert oversized["valid"] is False
    assert "more than 20" in oversized["message"]


def test_verify_input_accepts_a_one_digit_and_a_nine_digit_pmid():
    papers = [{"kind": "pmid", "value": "1"}, {"kind": "pmid", "value": "123456789"}]
    assert verifier.verify_input("pin_full_text", given(papers))["valid"] is True


def test_verify_output_accepts_the_subset(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_output("full_text_available", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is True
    assert verdict["score"] == 1.0


def test_verify_output_rejects_an_included_doi(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_output("full_text_available", given(), made([*KEPT, SAMPLE[1]]), str(tmp_path))
    assert verdict["valid"] is False
    assert "availability.json" in verdict["message"]


def test_verify_output_rejects_a_dropped_title(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_output("full_text_available", given(), made([SAMPLE[0]]), str(tmp_path))
    assert verdict["valid"] is False
    assert "availability.json" in verdict["message"]


def test_verify_output_rejects_a_swap(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_output("full_text_available", given(), made([SAMPLE[2], SAMPLE[0]]), str(tmp_path))
    assert verdict["valid"] is False
    assert "availability.json" in verdict["message"]


def test_verify_output_rejects_a_missing_file(tmp_path: Path):
    verdict = verifier.verify_output("full_text_available", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is False
    assert "missing" in verdict["message"]


def test_verify_output_rejects_malformed_json(tmp_path: Path):
    (tmp_path / "availability.json").write_text("{", encoding="utf-8")
    verdict = verifier.verify_output("full_text_available", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is False
    assert "JSON" in verdict["message"]


def test_verify_output_rejects_available_without_a_pmid(tmp_path: Path):
    rows = [{"kind": "pmid", "value": "100", "pmid": None, "available": True}]
    write_rows(tmp_path, rows)
    verdict = verifier.verify_output("full_text_available", given([SAMPLE[0]]), made([SAMPLE[0]]), str(tmp_path))
    assert verdict["valid"] is False
    assert "without a pmid" in verdict["message"]


def test_verify_output_rejects_a_repeated_output(tmp_path: Path):
    papers = [{"kind": "pmid", "value": "100"}, {"kind": "pmid", "value": "100"}]
    rows = [
        {"kind": "pmid", "value": "100", "pmid": "100", "available": True},
        {"kind": "pmid", "value": "100", "pmid": "100", "available": True},
    ]
    write_rows(tmp_path, rows)
    verdict = verifier.verify_output("full_text_available", given(papers), made(papers), str(tmp_path))
    assert verdict["valid"] is False
    assert "repeats" in verdict["message"]


def test_verify_output_rejects_rows_that_disagree(tmp_path: Path):
    papers = [{"kind": "pmid", "value": "100"}, {"kind": "pmid", "value": "100"}]
    rows = [
        {"kind": "pmid", "value": "100", "pmid": "100", "available": True},
        {"kind": "pmid", "value": "100", "pmid": "100", "available": False},
    ]
    write_rows(tmp_path, rows)
    verdict = verifier.verify_output("full_text_available", given(papers), made([papers[0]]), str(tmp_path))
    assert verdict["valid"] is False
    assert "disagrees" in verdict["message"]


def test_pin_output_does_not_need_a_file(tmp_path: Path):
    verdict = verifier.verify_output("pin_full_text", given(), made(KEPT), str(tmp_path))
    assert verdict["valid"] is True


def test_pin_output_rejects_a_malformed_pmid(tmp_path: Path):
    verdict = verifier.verify_output("pin_full_text", given(), made([{"kind": "pmid", "value": "0100"}]), str(tmp_path))
    assert verdict["valid"] is False
    assert "pmid" in verdict["message"]


def test_verify_task_accepts_an_exact_reference(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    output = made(KEPT)
    verdict = verifier.verify_task("pubmed-full-text-available", given(), output, output, str(tmp_path))
    assert verdict["valid"] is True
    assert verdict["score"] == 1.0


def test_verify_task_rejects_a_different_subset(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_task(
        "pubmed-full-text-available",
        given(),
        made([SAMPLE[0]]),
        made(KEPT),
        str(tmp_path),
    )
    assert verdict["valid"] is False
    assert "reference" in verdict["message"]


def test_verify_task_accepts_the_workspace_when_the_reference_is_absent(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_task("pubmed-full-text-available", given(), made(KEPT), None, str(tmp_path))
    assert verdict["valid"] is True
    absent = verifier.verify_task("pubmed-full-text-available", given(), made(KEPT), None, str(tmp_path / "empty"))
    assert absent["valid"] is False
    assert "missing" in absent["message"]


def test_verify_task_rejects_a_malformed_pmid(tmp_path: Path):
    write_rows(tmp_path, ROWS)
    verdict = verifier.verify_task(
        "pubmed-full-text-available",
        given(),
        made([{"kind": "pmid", "value": "12a"}]),
        made(KEPT),
        str(tmp_path),
    )
    assert verdict["valid"] is False
    assert "pmid" in verdict["message"]


def test_verify_task_rejects_a_file_that_disagrees_with_the_reference(tmp_path: Path):
    rows = [dict(row) for row in ROWS]
    rows[2] = {"kind": "title", "value": "A free paper", "pmid": "300", "available": False}
    write_rows(tmp_path, rows)
    output = made(KEPT)
    verdict = verifier.verify_task("pubmed-full-text-available", given(), output, output, str(tmp_path))
    assert verdict["valid"] is False
    assert "availability.json" in verdict["message"]


def test_empty_input_returns_an_empty_subset(tmp_path: Path):
    write_rows(tmp_path, [])
    output = made([])
    arguments = given([])
    assert verifier.verify_output("full_text_available", arguments, output, str(tmp_path))["valid"] is True
    verdict = verifier.verify_task("pubmed-full-text-available", arguments, output, output, str(tmp_path))
    assert verdict["valid"] is True


def test_every_paper_unavailable_returns_an_empty_subset(tmp_path: Path):
    rows = [dict(row, available=False) for row in ROWS]
    write_rows(tmp_path, rows)
    output = made([])
    assert verifier.verify_output("full_text_available", given(), output, str(tmp_path))["valid"] is True
    verdict = verifier.verify_task("pubmed-full-text-available", given(), output, output, str(tmp_path))
    assert verdict["valid"] is True


def test_a_repeated_free_pmid_appears_once(tmp_path: Path):
    papers = [{"kind": "pmid", "value": "100"}, {"kind": "pmid", "value": "100"}]
    rows = [
        {"kind": "pmid", "value": "100", "pmid": "100", "available": True},
        {"kind": "pmid", "value": "100", "pmid": "100", "available": True},
    ]
    write_rows(tmp_path, rows)
    output = made([papers[0]])
    assert verifier.verify_output("full_text_available", given(papers), output, str(tmp_path))["valid"] is True
    verdict = verifier.verify_task("pubmed-full-text-available", given(papers), output, output, str(tmp_path))
    assert verdict["valid"] is True


def test_a_resolved_pmid_that_is_not_free_stays_out(tmp_path: Path):
    papers = [{"kind": "doi", "value": "10.1000/xyz"}]
    rows = [{"kind": "doi", "value": "10.1000/xyz", "pmid": "200", "available": False}]
    write_rows(tmp_path, rows)
    output = made([])
    assert verifier.verify_output("full_text_available", given(papers), output, str(tmp_path))["valid"] is True


def test_titles_that_normalize_together_are_kept_once(tmp_path: Path):
    papers = [
        {"kind": "title", "value": "A free paper"},
        {"kind": "title", "value": "a free paper."},
    ]
    rows = [
        {"kind": "title", "value": "A free paper", "pmid": "300", "available": True},
        {"kind": "title", "value": "a free paper.", "pmid": "300", "available": True},
    ]
    write_rows(tmp_path, rows)
    output = made([papers[0]])
    assert verifier.verify_output("full_text_available", given(papers), output, str(tmp_path))["valid"] is True
