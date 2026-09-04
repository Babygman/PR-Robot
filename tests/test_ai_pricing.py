"""Test คำนวณค่าใช้จ่ายโดยประมาณจาก Token Usage (2026-09-04, สำหรับหน้า "ค่าใช้จ่าย AI")"""
from __future__ import annotations

from decimal import Decimal

from app.services.ai_pricing import calculate_cost_usd


def test_calculate_cost_usd_known_model():
    # gemini-3.6-flash: Input $0.75/1M, Output $3.75/1M (ตรวจสอบจริงจาก
    # https://ai.google.dev/gemini-api/docs/pricing 2026-09-04)
    cost = calculate_cost_usd("gemini-3.6-flash", prompt_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == Decimal("0.75") + Decimal("3.75")


def test_calculate_cost_usd_zero_tokens():
    assert calculate_cost_usd("gemini-3.6-flash", prompt_tokens=0, output_tokens=0) == Decimal("0")


def test_calculate_cost_usd_small_realistic_amounts():
    # ตัวอย่างใกล้เคียงการอ่านเอกสาร 1 ฉบับ (15,000 Input Token, 400 Output Token)
    cost = calculate_cost_usd("gemini-3.6-flash", prompt_tokens=15_000, output_tokens=400)
    expected = (Decimal(15_000) * Decimal("0.75") + Decimal(400) * Decimal("3.75")) / Decimal(
        1_000_000
    )
    assert cost == expected


def test_calculate_cost_usd_unknown_model_falls_back_to_default_rate():
    # Model ที่ไม่อยู่ในตาราง Pricing — ต้องไม่ Error และไม่คืนค่า 0 เงียบๆ (ใช้ Rate
    # Fallback ของ gemini-3.6-flash แทน)
    cost = calculate_cost_usd("some-future-model", prompt_tokens=1_000_000, output_tokens=0)
    assert cost == Decimal("0.75")
