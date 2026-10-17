"""テストの共通部品。"""
import json
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"

URL = "https://docs.google.com/spreadsheets/d/TESTID/edit"
VALUES = [["品名", "サイズ", "単重"]] + [
    [e["品名"], e["サイズ"], str(e["単重"])]
    for e in json.loads((FIXTURES / "unit_weights.json").read_text("utf-8"))
]


def client_returning(status: int, body: dict, seen: list | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def client_raising(exc: Exception) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc
    return httpx.Client(transport=httpx.MockTransport(handler))
