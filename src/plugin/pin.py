"""Reference tool: the same free-full-text subset, with no workspace file, pinned before the task runs."""

from __future__ import annotations

from pathlib import Path

from contract import FullTextInput, FullTextOutput
from plugin.client import get_client
from plugin.select import select_papers


def pin_full_text(given: FullTextInput, _workspace: Path) -> FullTextOutput:
    output, _papers = select_papers(given, get_client())
    return output
