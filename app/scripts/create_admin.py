"""Bootstrap Script — สร้าง Admin คนแรก (ก่อนมี Admin คนแรก ไม่มีใคร Login เข้ามาสร้าง
User ผ่าน API ได้เลย ต้องรันสคริปต์นี้ครั้งเดียวตอน Setup)

วิธีใช้ (จาก Virtual Environment ของโปรเจกต์, มี DATABASE_URL ใน .env แล้ว):
    python -m app.scripts.create_admin --name "ชื่อ" --email admin@example.com --password "xxxx"

ห้าม Hard-code Email/Password ในสคริปต์นี้ — รับผ่าน Argument เท่านั้น
(ตาม PROJECT_STANDARD.md ข้อ 8 Configuration and Secret Management)
"""
from __future__ import annotations

import argparse
import sys

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="สร้าง Admin User คนแรกของระบบ PR-Robot")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True, help="อย่างน้อย 8 ตัวอักษร")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("Error: password ต้องยาวอย่างน้อย 8 ตัวอักษร", file=sys.stderr)
        raise SystemExit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing is not None:
            print(f"Error: อีเมล {args.email} มีผู้ใช้ในระบบแล้ว (id={existing.id})", file=sys.stderr)
            raise SystemExit(1)

        user = User(
            name=args.name,
            email=args.email,
            password_hash=hash_password(args.password),
            is_admin=True,
            can_review=True,
            can_approve=True,
            can_receive=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"สร้าง Admin สำเร็จ: id={user.id} email={user.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
