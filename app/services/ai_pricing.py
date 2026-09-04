"""ตาราง Pricing ของ Gemini API + คำนวณค่าใช้จ่ายโดยประมาณต่อ Transaction (2026-09-04,
Feedback จริงจากผู้ใช้ — อยากเห็นค่าใช้จ่าย AI ในระบบหลัง Upgrade ออกจาก Free Tier)

อ้างอิงราคาจริงจาก https://ai.google.dev/gemini-api/docs/pricing (ตรวจสอบ 2026-09-04,
Standard Tier ไม่ใช่ Batch/Flex/Priority) — **ต้องอัปเดตตารางนี้เองถ้า Google เปลี่ยน
ราคาในอนาคต** ไม่มีกลไก Auto-sync ราคาจาก Google — ค่าที่คำนวณแล้วบันทึกไว้ใน Database
ตอน Transaction เกิดขึ้นเป็น Snapshot ณ เวลานั้น จะไม่ถูกคำนวณซ้ำทีหลังแม้ตารางนี้จะถูก
แก้ไขต่อไป (ดู app/models/ai_usage_log.py)
"""
from __future__ import annotations

from decimal import Decimal

# {model_name: (input_usd_per_1m_tokens, output_usd_per_1m_tokens)}
# output รวม Thinking Token ด้วย (Billed ในอัตราเดียวกับ Output ปกติ)
_MODEL_PRICING_USD_PER_1M: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-3.6-flash": (Decimal("0.75"), Decimal("3.75")),
}

# Fallback ถ้าเปลี่ยน GEMINI_MODEL ใน .env เป็นตัวที่ยังไม่มีในตารางด้านบน — ใช้ Rate ของ
# gemini-3.6-flash ไปก่อนเพื่อไม่ให้ค่าใช้จ่ายหายไปเป็น 0 เงียบๆ (ดีกว่าไม่มีตัวเลขเลย
# แต่ควรเพิ่ม Model ใหม่เข้าตารางด้านบนจริงๆ ถ้าเปลี่ยน Model ถาวร)
_DEFAULT_PRICING_USD_PER_1M = _MODEL_PRICING_USD_PER_1M["gemini-3.6-flash"]


def calculate_cost_usd(model: str, prompt_tokens: int, output_tokens: int) -> Decimal:
    """คำนวณค่าใช้จ่ายโดยประมาณ (USD) จากจำนวน Token จริงที่ Gemini ตอบกลับมา"""
    input_rate, output_rate = _MODEL_PRICING_USD_PER_1M.get(model, _DEFAULT_PRICING_USD_PER_1M)
    cost = (
        Decimal(prompt_tokens) * input_rate + Decimal(output_tokens) * output_rate
    ) / Decimal(1_000_000)
    return cost
