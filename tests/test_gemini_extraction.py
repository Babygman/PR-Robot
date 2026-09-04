"""Test Retry อัตโนมัติของ GeminiExtractionService (เพิ่ม 2026-09-03 หลังเจอ
503 UNAVAILABLE จริงตอน UAT Walkthrough — ไม่ยิง Network จริง ใช้ Fake Client แทน
เหมือน tests/test_documents.py"""
from __future__ import annotations

from typing import Any

import docx
import openpyxl
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
    def __init__(self) -> None:
        self.call_count = 0

    def upload(self, file: str) -> Any:
        self.call_count += 1
        return object()


class _FakeModels:
    """จำลอง client.models.generate_content — Raise Error ตามคิวที่ตั้งไว้ก่อน สุดท้าย
    ค่อยสำเร็จ (หรือ Raise ตลอดถ้าคิว Error ยาวกว่าจำนวนครั้งที่ทดสอบ)"""

    def __init__(self, errors_then_success: list[Exception | None]) -> None:
        self._queue = list(errors_then_success)
        self.call_count = 0
        self.last_kwargs: dict[str, Any] = {}

    def generate_content(self, **kwargs: Any) -> _FakeResponse:
        self.call_count += 1
        self.last_kwargs = kwargs
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


# Word/Excel/CSV/TXT (2026-09-04, Feedback จริงจากผู้ใช้) — ต้องแตกข้อความออกมาก่อนแล้ว
# ส่งเป็น Text Content Part แทนการอัปโหลดไฟล์ดิบแบบ Vision (files.upload ต้องไม่ถูกเรียก
# เลยสำหรับไฟล์กลุ่มนี้ — ต่างจาก PDF/รูปภาพด้านบนที่ผ่าน Vision เสมอ)


def test_extract_docx_reads_paragraphs_and_tables_as_text(tmp_path):
    file_path = tmp_path / "quote.docx"
    document = docx.Document()
    document.add_paragraph("ใบเสนอราคา จาก บริษัท ทดสอบ จำกัด")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "กระดาษ A4"
    table.rows[0].cells[1].text = "10 รีม"
    document.save(file_path)

    client = _FakeClient([])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, sleep_fn=sleep_fn)

    result = service.extract(str(file_path))

    assert result.vendor_name == "บริษัท ทดสอบ จำกัด"
    assert client.files.call_count == 0  # ต้องไม่ผ่าน Vision/files.upload
    text_sent = client.models.last_kwargs["contents"][1]
    assert "ใบเสนอราคา" in text_sent
    assert "กระดาษ A4 | 10 รีม" in text_sent


def test_extract_xlsx_reads_cell_values_as_text(tmp_path):
    file_path = tmp_path / "quote.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["Product", "Quantity", "Unit Price"])
    sheet.append(["กระดาษ A4", 10, 120.5])
    workbook.save(file_path)

    client = _FakeClient([])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, sleep_fn=sleep_fn)

    result = service.extract(str(file_path))

    assert result.vendor_name == "บริษัท ทดสอบ จำกัด"
    assert client.files.call_count == 0
    text_sent = client.models.last_kwargs["contents"][1]
    assert "Sheet1" in text_sent
    assert "กระดาษ A4 | 10 | 120.5" in text_sent


def test_extract_csv_reads_rows_as_text(tmp_path):
    file_path = tmp_path / "quote.csv"
    file_path.write_text("Product,Quantity\nกระดาษ A4,10\n", encoding="utf-8")

    client = _FakeClient([])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, sleep_fn=sleep_fn)

    result = service.extract(str(file_path))

    assert result.vendor_name == "บริษัท ทดสอบ จำกัด"
    assert client.files.call_count == 0
    text_sent = client.models.last_kwargs["contents"][1]
    assert "กระดาษ A4 | 10" in text_sent


def test_extract_txt_reads_raw_text(tmp_path):
    file_path = tmp_path / "note.txt"
    file_path.write_text("ใบเสนอราคา กระดาษ A4 จำนวน 10 รีม", encoding="utf-8")

    client = _FakeClient([])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, sleep_fn=sleep_fn)

    result = service.extract(str(file_path))

    assert result.vendor_name == "บริษัท ทดสอบ จำกัด"
    assert client.files.call_count == 0
    text_sent = client.models.last_kwargs["contents"][1]
    assert "กระดาษ A4 จำนวน 10 รีม" in text_sent


def test_extract_empty_txt_raises_without_calling_gemini(tmp_path):
    file_path = tmp_path / "empty.txt"
    file_path.write_text("   \n  ", encoding="utf-8")  # มีแต่ Whitespace

    client = _FakeClient([])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, sleep_fn=sleep_fn)

    with pytest.raises(GeminiExtractionError, match="ไม่พบข้อความ"):
        service.extract(str(file_path))

    assert client.models.call_count == 0  # ไม่ควรยิงไป Gemini เลยถ้าไฟล์ว่าง
    assert sleep_calls == []


def test_extract_corrupt_docx_raises_without_retry(tmp_path):
    file_path = tmp_path / "broken.docx"
    file_path.write_bytes(b"not a real docx file")

    client = _FakeClient([])
    sleep_calls, sleep_fn = _make_sleep_recorder()
    service = GeminiExtractionService(client=client, max_attempts=3, sleep_fn=sleep_fn)

    with pytest.raises(GeminiExtractionError, match="อ่านเนื้อหาไฟล์ไม่สำเร็จ"):
        service.extract(str(file_path))

    assert client.models.call_count == 0  # อ่านไฟล์เสียซ้ำก็ผิดเหมือนเดิม ไม่ควร Retry
    assert sleep_calls == []
