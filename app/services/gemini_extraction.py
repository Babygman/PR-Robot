"""เรียก Google Gemini API สกัดข้อมูลจากเอกสารต้นทาง (ใบเสนอราคา/ใบรับของ)

ใช้ SDK ใหม่ google-genai (google-generativeai รุ่นเก่าเลิกใช้แล้วตั้งแต่ปี 2025)
Model กำหนดผ่าน .env (GEMINI_MODEL) ไม่ Hardcode เพื่อให้ปรับได้ตาม Quota จริงของ API Key

Client ถูกออกแบบให้ Inject แทนที่ได้ (Dependency Injection) เพื่อให้ Unit Test
ไม่ต้องยิง Network จริงไปหา Gemini — ทดสอบด้วย Fake Client แทน
"""
from __future__ import annotations

from google import genai
from google.genai import types

from app.core.config import settings
from app.schemas.source_document import ExtractionResult

_EXTRACTION_PROMPT = """\
คุณคือระบบสกัดข้อมูลจากเอกสารจัดซื้อ (ใบเสนอราคา หรือ ใบรับของ) ให้แม่นยำที่สุดเท่าที่ทำได้
อ่านเอกสารที่แนบมาแล้วดึงข้อมูลต่อไปนี้:
- vendor_name: ชื่อผู้ขาย/ร้านค้า
- document_no: เลขที่เอกสาร
- document_date: วันที่เอกสาร (รูปแบบ YYYY-MM-DD)
- items: รายการสินค้าทุกรายการ พร้อม description, quantity, unit, unit_price, amount (ถ้ามี)
- notes: หมายเหตุอื่นที่เกี่ยวข้องกับการจัดซื้อ
- ai_confidence: ประเมินความมั่นใจของคุณเองว่าอ่านข้อมูลถูกต้องครบถ้วนแค่ไหน (ตัวเลข 0.0-1.0)

กฎสำคัญ: ถ้าอ่านข้อมูลใดไม่ได้หรือไม่มีในเอกสาร ให้เว้นว่างไว้ (null) ห้ามเดาหรือสร้างข้อมูลที่ไม่มีในเอกสารขึ้นมาเอง
"""


class GeminiExtractionError(Exception):
    """เกิดข้อผิดพลาดระหว่างเรียก Gemini API หรือแปลงผลลัพธ์เป็น JSON ตาม Schema"""


class GeminiExtractionService:
    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        if client is None:
            if not settings.gemini_api_key:
                raise GeminiExtractionError("ยังไม่ได้ตั้งค่า GEMINI_API_KEY ใน .env")
            client = genai.Client(api_key=settings.gemini_api_key)
        self._client = client
        self._model = model or settings.gemini_model

    def extract(self, file_path: str) -> ExtractionResult:
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
        except GeminiExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001 - ห่อ Exception ทุกชนิดจาก SDK ภายนอกเป็น Error ของเราเอง
            raise GeminiExtractionError(f"เรียก Gemini API ไม่สำเร็จ: {exc}") from exc

        if not response.text:
            raise GeminiExtractionError("Gemini ไม่ส่งข้อมูลกลับมา (Response ว่างเปล่า)")

        try:
            return ExtractionResult.model_validate_json(response.text)
        except Exception as exc:  # noqa: BLE001
            raise GeminiExtractionError(
                f"แปลงผลลัพธ์จาก Gemini เป็น JSON ตาม Schema ไม่สำเร็จ: {exc}"
            ) from exc
