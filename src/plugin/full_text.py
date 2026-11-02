"""The task tool: record which papers PubMed marks as free full text."""

from __future__ import annotations

import json
from pathlib import Path

from contract import FullTextInput, FullTextOutput
from plugin.client import get_client
from plugin.select import select_papers

AVAILABILITY_FILE = "availability.json"


def full_text_available(given: FullTextInput, workspace: Path) -> FullTextOutput:
    output, papers = select_papers(given, get_client())
    payload = {"papers": papers}
    (workspace / AVAILABILITY_FILE).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output
