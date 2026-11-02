"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    FULL_TEXT_AVAILABLE = "full_text_available"
    PIN_FULL_TEXT = "pin_full_text"


class Task(Enum):
    PUBMED_FULL_TEXT_AVAILABLE = "pubmed-full-text-available"


class PaperKind(Enum):
    PMID = "pmid"
    DOI = "doi"
    TITLE = "title"


@dataclass
class Paper(Output):
    kind: Annotated[PaperKind, "Whether value is a PMID, a DOI, or an article title"]
    value: Annotated[str, "The PMID, DOI, or article title"]


@dataclass
class FullTextInput(Output):
    papers: Annotated[list[Paper], "Papers to check, in caller order, at most 20"]


@dataclass
class FullTextOutput(Output):
    available: Annotated[
        list[Paper],
        "Input papers whose PubMed record is in the free full text subset, in input order, duplicates removed",
    ]


TOOLS = {
    Tool.FULL_TEXT_AVAILABLE: (FullTextInput, FullTextOutput),
    Tool.PIN_FULL_TEXT: (FullTextInput, FullTextOutput),
}
TASKS = {Task.PUBMED_FULL_TEXT_AVAILABLE: (FullTextInput, FullTextOutput)}
