"""Test Retry อัตโนมัติของ GeminiExtractionService (เพิ่ม 2026-09-03 หลังเจอ
503 UNAVAILABLE จริงตอน UAT Walkthrough — ไม่ยิง Network จริง ใช้ Fake Client แทน
เหมือน tests/test_documents.py"""
from __future__ import annotations

from typing import Any

import pytest
from google.genai import errors as genai_errors

from app.services.gemini_extraction import GeminiExtractionError, GeminiExtractionService

_VALID_JSON = (
    '{"vendor_name": "บริษัท ทดสอบ จำกัด", "items": '
    '[{"description": "กระดาษ A4", "quantity": "10", "unit": "รีม"}]}'
)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeFiles:
    def upload(self, file: str) -> Any:
        return object()


class _FakeModels:
    """จำลอง client.models.generate_content — Raise Error ตามคิวที่ตั้งไว้ก่อน สุดท้าย
    ค่อยสำเร็จ (หรือ Raise ตลอดถ้าคิว Error ยาวกว่าจำนวนครั้งที่ทดสอบ)"""

    def __init__(self, errors_then_success: list[Exception | None]) -> None:
        self._queue = list(errors_then_success)
        self.call_count = 0

    def generate_content(self, **kwargs: Any) -> _FakeResponse:
        self.call_count += 1
        outcome = self._queue.pop(0) if self._queue else None
        if outcome is not None:
            raise outcome
        return _FakeResponse(_VALID_JSON)


class _FakeClient:
    def __init__(self, errors_then_success: list[Exception | None]) -> None:
        self.files = _FakeFiles()
        self.models = _FakeModels(errors_then_success)


def _server_error(code: int, status: str) -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"message": "จำลอง Error", "status": status})


def _client_error(code: int, status: str) -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"message": "จำลอง Error", "status": status})


def _make_sleep_recorder() -> tuple[list[float], object]:
    calls: list[float] = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    return calls, _sleep


def test_extract_succeeds_first_try_no_retry():
    client = _FakeClient([])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, model="gemini-3.6-flash", sleep_fn=sleep_fn)

    result = service.extract("dummy.pdf")

    assert result.vendor_name == "บริษัท ทดสอบ จำกัด"
    assert client.models.call_count == 1
    assert sleep_calls == []


def test_extract_retries_on_503_then_succeeds():
    client = _FakeClient([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(
        client=client,
        model="gemini-3.6-flash",
        max_attempts=3,
        backoff_base_seconds=2.0,
        sleep_fn=sleep_fn,
    )

    result = service.extract("dummy.pdf")

    assert result.vendor_name == "บริษัท ทดสอบ จำกัด"
    assert client.models.call_count == 3
    # Exponential Backoff: 2 วิ (ครั้งที่ 1->2), 4 วิ (ครั้งที่ 2->3)
    assert sleep_calls == [2.0, 4.0]


def test_extract_retries_on_429_rate_limit():
    client = _FakeClient([_client_error(429, "RESOURCE_EXHAUSTED")])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, max_attempts=3, sleep_fn=sleep_fn)

    result = service.extract("dummy.pdf")

    assert result.vendor_name == "บริษัท ทดสอบ จำกัด"
    assert client.models.call_count == 2
    assert len(sleep_calls) == 1


def test_extract_does_not_retry_on_404_not_found():
    """404 (ชื่อ Model ผิด/เลิกให้บริการแล้ว) เป็น Error ถาวร — Retry ไปก็ได้ผลเดิม
    ต้อง Fail ทันทีไม่ต้องรอ (Bug จริงที่เจอ 2026-09-03: model gemini-2.5-flash
    เลิกให้บริการ)"""
    client = _FakeClient([_client_error(404, "NOT_FOUND")])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, max_attempts=3, sleep_fn=sleep_fn)

    with pytest.raises(GeminiExtractionError, match="404"):
        service.extract("dummy.pdf")

    assert client.models.call_count == 1
    assert sleep_calls == []


def test_extract_gives_up_after_max_attempts_on_persistent_503():
    persistent_503 = _server_error(503, "UNAVAILABLE")
    client = _FakeClient([persistent_503, persistent_503, persistent_503])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, max_attempts=3, sleep_fn=sleep_fn)

    with pytest.raises(GeminiExtractionError, match="503"):
        service.extract("dummy.pdf")

    assert client.models.call_count == 3
    assert len(sleep_calls) == 2  # Retry แค่ระหว่างครั้งที่ 1->2 และ 2->3 ไม่ Retry หลังครั้งสุดท้าย


def test_extract_empty_response_text_raises_without_retry():
    class _EmptyModels:
        call_count = 0

        def generate_content(self, **kwargs: Any) -> _FakeResponse:
            _EmptyModels.call_count += 1
            return _FakeResponse("")

    client = _FakeClient([])
    client.models = _EmptyModels()
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, sleep_fn=sleep_fn)

    with pytest.raises(GeminiExtractionError, match="ว่างเปล่า"):
        service.extract("dummy.pdf")

    assert sleep_calls == []


def test_extract_invalid_json_raises_without_retry():
    class _BadJsonModels:
        def generate_content(self, **kwargs: Any) -> _FakeResponse:
            return _FakeResponse("not valid json")

    client = _FakeClient([])
    client.models = _BadJsonModels()
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, sleep_fn=sleep_fn)

    with pytest.raises(GeminiExtractionError, match="แปลงผลลัพธ์"):
        service.extract("dummy.pdf")

    assert sleep_calls == []
