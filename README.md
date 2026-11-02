# PubMed Full Text

A `nanoagent.plugin/v0001` plugin, created by `nanoagent plugin new` with the
structure of NanoAgent's reference plugin,
[arxiv-source](https://github.com/zeyuyang8/arxiv-source).

Given papers identified by PMID, DOI, or title, it returns the subset whose
PubMed record is in the `free full text[sb]` subset.

## Tools

| Tool | Does | Code |
|---|---|---|
| `full_text_available` | Resolves each paper and returns the ones PubMed marks as free full text | `src/plugin/full_text.py` |
| `pin_full_text` | Computes the same subset as the task's answer key, and writes no file | `src/plugin/pin.py` |

`full_text_available` writes `availability.json` in the workspace: one row per input paper, with the resolved PMID or null and whether that PMID is in the free full text subset. A PMID, DOI, or title that resolves to no record is left out. A DOI or exact title that matches more than one record raises. The same kind and normalized value is kept once, at its first occurrence. At most 20 papers are accepted.

### Tasks

| Task | Does | Runner |
|---|---|---|
| `pubmed-full-text-available` | Returns the free-full-text subset | `tool`, with `full_text_available` and reference `pin_full_text` |

The input is `papers`, each with `kind` (`pmid`, `doi`, or `title`) and `value`. The output is `available`, those input papers in order.

## Layout

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # environment variable NAMEs this plugin needs, never values
├── src/plugin/      # the MCP server: __main__.py, its IMPLEMENTATIONS, and the plugin's own modules
├── tests/
├── ui/              # how the page draws the outputs: renderers.js and renderers.css
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier package
```

`contract.py` is the one place a value's shape is declared. Its `Output`
classes are the JSON Schemas the server offers and the agent sees, and every
input and output is built into its class on the way in and out: the server,
NanoAgent and the verifier all get typed values, never loose dicts. A tool
that fails raises; NanoAgent sees an MCP error.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
```

The tests use a fake HTTP client and do not call NCBI. A live run needs
network access to `eutils.ncbi.nlm.nih.gov`. `NCBI_API_KEY` and `NCBI_EMAIL`
are listed in `.env`. The client sends them on the E-utilities request when
they are non-empty, and still resolves papers when they are empty. No
workspace file is required before a run; `full_text_available` creates
`availability.json`.
