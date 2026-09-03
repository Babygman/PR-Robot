"""เรียก Google Gemini API สกัดข้อมูลจากเอกสารต้นทาง (ใบเสนอราคา/ใบรับของ)

ใช้ SDK ใหม่ google-genai (google-generativeai รุ่นเก่าเลิกใช้แล้วตั้งแต่ปี 2025)
Model กำหนดผ่าน .env (GEMINI_MODEL) ไม่ Hardcode เพื่อให้ปรับได้ตาม Quota จริงของ API Key

Client ถูกออกแบบให้ Inject แทนที่ได้ (Dependency Injection) เพื่อให้ Unit Test
ไม่ต้องยิง Network จริงไปหา Gemini — ทดสอบด้วย Fake Client แทน
"""
from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import settings
from app.schemas.source_document import ExtractionResult

_EXTRACTION_PROMPT = """\
คุณคือระบบสกัดข้อมูลจากเอกสารจัดซื้อของบริษัท Sunstar Chemical (Thailand) ให้แม่นยำ
ที่สุดเท่าที่ทำได้ เอกสารอาจเป็นใบเสนอราคา ใบยืมสินค้า ใบส่งสินค้า หรือใบรับของ — และมา
จาก Supplier ได้หลายรายที่มีรูปแบบตารางไม่เหมือนกันเลย (ตำแหน่งคอลัมน์ ชื่อหัวตาราง ภาษา
ที่ใช้ ต่างกันได้) ให้อ่านตามความหมายของแต่ละส่วนในเอกสารจริง ไม่ใช่ตำแหน่งตายตัว

อ่านเอกสารที่แนบมาแล้วดึงข้อมูลต่อไปนี้:
- detected_doc_type: ประเภทเอกสารที่คุณอ่านออกจากเนื้อหา ต้องเป็นค่าใดค่าหนึ่งนี้เท่านั้น
  "quotation" (ใบเสนอราคา), "receiving_note" (ใบรับของ), "borrow_note" (ใบยืมสินค้า),
  "delivery_note" (ใบส่งสินค้า), หรือ "other" ถ้าไม่แน่ใจ
- vendor_name: ชื่อผู้ขาย/ร้านค้า/Supplier
- document_no: เลขที่เอกสาร
- document_date: วันที่เอกสาร (รูปแบบ YYYY-MM-DD)
- items: รายการสินค้าทุกรายการ แยกฟิลด์ต่อไปนี้ให้ชัดเจนที่สุด (เอกสารส่วนใหญ่มีคอลัมน์
  แยกกันอยู่แล้ว):
  - product_name: ชื่อสินค้า (เช่น คอลัมน์ "PRODUCT NAME")
  - description: รายละเอียด/สเปกสินค้า (เช่น คอลัมน์ "PRODUCT DESCRIPTION" ขนาด/มิติ)
  - color: สี (ถ้ามีคอลัมน์แยก เช่น "COLOR")
  - quantity: จำนวน (ตัวเลขล้วนๆ ไม่รวมหน่วย)
  - unit: หน่วยนับ (เช่น Roll, ชิ้น, กก. — เอกสารบางแบบย่อไว้เช่น "R." ให้ขยายเป็นคำเต็ม
    ถ้ามั่นใจความหมาย เช่น "R." มักหมายถึง "Roll")
  - unit_price, amount: ราคาต่อหน่วย/ราคารวม ถ้ามี
- notes: หมายเหตุอื่นที่เกี่ยวข้องกับการจัดซื้อ
- ai_confidence: ประเมินความมั่นใจของคุณเองว่าอ่านข้อมูลถูกต้องครบถ้วนแค่ไหน (ตัวเลข 0.0-1.0)

กฎสำคัญ: ถ้าอ่านข้อมูลใดไม่ได้หรือไม่มีในเอกสาร ให้เว้นว่างไว้ (null) ห้ามเดาหรือสร้างข้อมูลที่ไม่มีในเอกสารขึ้นมาเอง
"""


# Auto-Retry (เพิ่ม 2026-09-03 หลังเจอจริงตอน UAT Walkthrough): Gemini ตอบ
# "503 UNAVAILABLE... currently experiencing high demand" เป็นระยะ — เป็น Error ชั่วคราว
# ฝั่ง Google เอง ไม่ใช่ปัญหาโค้ดเรา จึง Retry อัตโนมัติแบบ Exponential Backoff ให้ก่อน
# ค่อย Fail จริง (ลดการรบกวนผู้ใช้ให้กด Upload ซ้ำเอง)
_RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 2.0  # Exponential: รอ 2 วิ แล้ว 4 วิ ระหว่างครั้งที่ Retry


def _is_retryable(exc: Exception) -> bool:
    """แยก Error ชั่วคราว (ควร Retry) ออกจาก Error ถาวร (Retry ไปก็ได้ผลเดิม เสียเวลา
    ผู้ใช้รอเปล่าๆ) — Retryable: Rate Limit (429), Server Error ฝั่ง Google (5xx เช่น
    503 High Demand ที่เจอจริง), Network Timeout/Connection Error — ไม่ Retryable:
    Client Error อื่น เช่น 404 (พิมพ์ชื่อ Model ผิด/Model เลิกให้บริการแล้ว — ดู
    Bug จริงที่เจอวันเดียวกัน 2026-09-03), 400 (Request ผิด), 401/403 (Auth ผิด)
    """
    if isinstance(exc, genai_errors.APIError):
        return exc.code in _RETRYABLE_HTTP_STATUS_CODES
    _retryable_network_errors = (
        httpx.TimeoutException
        | httpx.ConnectError
        | httpx.ReadError
        | ConnectionError
        | TimeoutError
    )
    if isinstance(exc, _retryable_network_errors):
        return True
    return False


class GeminiExtractionError(Exception):
    """เกิดข้อผิดพลาดระหว่างเรียก Gemini API หรือแปลงผลลัพธ์เป็น JSON ตาม Schema"""


class GeminiExtractionService:
    def __init__(
        self,
        client: genai.Client | None = None,
        model: str | None = None,
        max_attempts: int = _MAX_ATTEMPTS,
        backoff_base_seconds: float = _BACKOFF_BASE_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if client is None:
            if not settings.gemini_api_key:
                raise GeminiExtractionError("ยังไม่ได้ตั้งค่า GEMINI_API_KEY ใน .env")
            client = genai.Client(api_key=settings.gemini_api_key)
        self._client = client
        self._model = model or settings.gemini_model
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        # sleep_fn Inject ได้เพื่อให้ Unit Test ไม่ต้องรอจริงตอน Retry (ดู
        # tests/test_gemini_extraction.py)
        self._sleep = sleep_fn

    def extract(self, file_path: str) -> ExtractionResult:
        response = None
        last_exc: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                uploaded_file = self._client.files.upload(file=file_path)
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=[_EXTRACTION_PROMPT, uploaded_file],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=ExtractionResult.model_json_schema(),
                    ),
                )
                break
            except Exception as exc:  # noqa: BLE001 - ห่อ Exception ทุกชนิดจาก SDK ภายนอกเป็น Error ของเราเอง
                last_exc = exc
                if _is_retryable(exc) and attempt < self._max_attempts:
                    self._sleep(self._backoff_base_seconds * (2 ** (attempt - 1)))
                    continue
                raise GeminiExtractionError(f"เรียก Gemini API ไม่สำเร็จ: {exc}") from exc

        if response is None:  # กันไว้เผื่อ Logic พลาด (ไม่ควรเกิดขึ้นจริง)
            raise GeminiExtractionError(f"เรียก Gemini API ไม่สำเร็จ: {last_exc}")

        if not response.text:
            raise GeminiExtractionError("Gemini ไม่ส่งข้อมูลกลับมา (Response ว่างเปล่า)")

        try:
            return ExtractionResult.model_validate_json(response.text)
        except Exception as exc:  # noqa: BLE001
            raise GeminiExtractionError(
                f"แปลงผลลัพธ์จาก Gemini เป็น JSON ตาม Schema ไม่สำเร็จ: {exc}"
            ) from exc
