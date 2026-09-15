"""Signer Snapshot — Electronic Signature Hardening (2026-09-15, Design §3.2)

Snapshot ข้อมูลผู้เซ็น (ชื่อ/อีเมล/ตำแหน่ง/แผนก) ลงใน AuditLog.detail ทันทีที่เซ็นจริง
แทนที่จะ Join สดจาก users ตอนแสดงผล (หน้าเว็บยังคง Resolve ชื่อสดผ่าน resolve_user_names
เหมือนเดิมเพื่อความสะดวก — Snapshot นี้คือสำเนาที่ระเบิดไม่ได้สำหรับอ้างอิงย้อนหลัง 5-10 ปี
เท่านั้น) กันปัญหาแก้ไขข้อมูล User ภายหลัง (เปลี่ยนชื่อ/ตำแหน่ง/แผนก) แล้วประวัติเก่าที่
เคย "เซ็น" ไปแล้วดูเหมือนเปลี่ยนตามไปด้วย — ใช้เฉพาะจุด "เซ็น" จริงเท่านั้น (Submit/
Approve/Reject/FA Acknowledge ของทั้ง PR/AR) ไม่ใช่ทุกจุดที่เขียน AuditLog (Attachment
Upload/Log ทั่วไปไม่ใช่การเซ็น ไม่ต้อง Snapshot)"""
from __future__ import annotations

from app.models import User


def build_signer_snapshot(user: User) -> dict:
    return {
        "name": user.name,
        "email": user.email,
        "position": user.position,
        "department": user.department,
    }
