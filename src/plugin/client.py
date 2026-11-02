"""HTTP client for NCBI E-utilities. Tests replace it with set_client."""

from __future__ import annotations

import json
import os
import time

import httpx

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
TOOL_NAME = "pubmed-full-text-available"

_client = None


class HttpxClient:
    """One process-wide client. A second request waits so NCBI's rate limit is respected."""

    def __init__(self, transport=None, pause=None):
        self._http = httpx.Client(timeout=30.0, transport=transport)
        self._pause = pause
        self._calls = 0

    def get_json(self, url: str, params: dict[str, str]) -> dict:
        if self._calls:
            time.sleep(self._pause_seconds())
        self._calls += 1
        response = self._http.get(url, params=params)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code} from {url}")
        try:
            body = response.json()
        except json.JSONDecodeError as error:
            raise RuntimeError(f"response from {url} was not JSON") from error
        if not isinstance(body, dict):
            raise TypeError(f"response from {url} was not a JSON object")
        return body

    def _pause_seconds(self) -> float:
        if self._pause is not None:
            return self._pause
        if os.environ.get("NCBI_API_KEY", "").strip():
            return 0.11
        return 0.34


def get_client():
    global _client
    if _client is None:
        _client = HttpxClient()
    return _client


def set_client(client) -> None:
    global _client
    _client = client
