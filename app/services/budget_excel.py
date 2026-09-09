"""Budget Control — Excel Upload Parser/Validator/Upsert (Phase 10, 2026-09-09)

Format (ดู docs/drafts/budget_control_design_draft.md §4):
department | budget_type | account_code | period_start | period_end | budget_name
(Optional) | budgeted_amount

Import แบบ Partial-success — แถวผิดไม่บล็อกแถวถูก บันทึก Log ทุกครั้งที่ Upload ลง
budget_upload_batches + budget_upload_row_errors (เฉพาะแถวที่ Error)

Re-upload (Merge/Update): จับคู่ด้วย department+budget_type+account_code+period_start+
period_end ทั้งหมด — ถ้าตรงเป๊ะทุก Field ถือเป็นแถวเดิม อัปเดตแค่ budgeted_amount/
budget_name (ไม่แตะ used_amount เด็ดขาด) ถ้าไม่ตรงถือเป็นแถวใหม่แยกต่างหาก

Validate ตอน Upload: เตือน (ไม่บล็อก) ถ้าพบช่วงเวลาที่ทับซ้อนกันสำหรับ
Department+Type+Code เดียวกัน — ให้ Admin/FA เห็น Warning ในผลลัพธ์แต่ยัง Upsert
สำเร็จตามปกติ
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ARBudgetType, BudgetMaster, BudgetUploadBatch, BudgetUploadRowError

_REQUIRED_COLUMNS = [
    "department",
    "budget_type",
    "account_code",
    "period_start",
    "period_end",
    "budgeted_amount",
]
_ALL_COLUMNS = _REQUIRED_COLUMNS + ["budget_name"]


@dataclass
class _RowOutcome:
    row_no: int
    ok: bool
    message: str
    department: str | None = None
    account_code: str | None = None
    raw_data: dict = field(default_factory=dict)


def _parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        return None


def _read_rows(file_bytes: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return []

    header_map: dict[int, str] = {}
    for idx, cell in enumerate(header_row):
        if cell is None:
            continue
        key = str(cell).strip().lower()
        if key in _ALL_COLUMNS:
            header_map[idx] = key

    rows: list[dict] = []
    for raw in rows_iter:
        if raw is None or all(v is None for v in raw):
            continue
        row = {col: (raw[idx] if idx < len(raw) else None) for idx, col in header_map.items()}
        if not row:
            continue
        rows.append(row)
    return rows


def _validate_row(row: dict) -> tuple[dict | None, str | None]:
    missing = [c for c in _REQUIRED_COLUMNS if not row.get(c) and row.get(c) != 0]
    if missing:
        return None, f"ขาดข้อมูลจำเป็น: {', '.join(missing)}"

    department = str(row["department"]).strip()
    budget_type_raw = str(row["budget_type"]).strip().lower()
    if budget_type_raw not in {"expenses", "assets"}:
        return None, f'budget_type ต้องเป็น "expenses" หรือ "assets" เท่านั้น (ได้ "{budget_type_raw}")'

    account_code = str(row["account_code"]).strip()
    period_start = _parse_date(row["period_start"])
    period_end = _parse_date(row["period_end"])
    if period_start is None or period_end is None:
        return None, "period_start/period_end ไม่ใช่รูปแบบวันที่ที่ถูกต้อง (dd/mm/yyyy)"
    if period_start > period_end:
        return None, "period_start ต้องไม่เกิน period_end"

    budgeted_amount = _parse_decimal(row["budgeted_amount"])
    if budgeted_amount is None:
        return None, "budgeted_amount ไม่ใช่ตัวเลขที่ถูกต้อง"
    if budgeted_amount < 0:
        return None, "budgeted_amount ต้องไม่ติดลบ"

    budget_name = str(row["budget_name"]).strip() if row.get("budget_name") else None

    return (
        {
            "department": department,
            "budget_type": ARBudgetType(budget_type_raw),
            "account_code": account_code,
            "period_start": period_start,
            "period_end": period_end,
            "budgeted_amount": budgeted_amount,
            "budget_name": budget_name,
        },
        None,
    )


def parse_and_upsert(
    db: Session, *, filename: str, file_bytes: bytes, uploaded_by_id: int
) -> tuple[BudgetUploadBatch, list[_RowOutcome]]:
    """Parse + Validate + Upsert ทั้งไฟล์ในครั้งเดียว — สร้าง BudgetUploadBatch พร้อม
    BudgetUploadRowError ของแถวที่ Error แล้ว flush() ให้ Caller เห็น batch.id ก่อน
    Caller เป็นคน commit() เอง (Pattern เดียวกับ Route อื่นในโปรเจกต์) คืนค่าเป็น
    (batch, outcomes) ให้ Route แปลง outcomes เป็น Response เอง
    """
    try:
        rows = _read_rows(file_bytes)
    except Exception as exc:  # noqa: BLE001 — ไฟล์เสีย/ไม่ใช่ Excel จริง แปลงเป็น Error แถวเดียว
        batch = BudgetUploadBatch(
            filename=filename,
            uploaded_by_id=uploaded_by_id,
            total_rows=0,
            success_rows=0,
            error_rows=1,
        )
        db.add(batch)
        db.flush()
        db.add(
            BudgetUploadRowError(
                batch_id=batch.id, row_no=0, error_message=f"อ่านไฟล์ไม่สำเร็จ: {exc}", raw_data=None
            )
        )
        return batch, [_RowOutcome(row_no=0, ok=False, message=f"อ่านไฟล์ไม่สำเร็จ: {exc}")]

    outcomes: list[_RowOutcome] = []
    seen_keys: set[tuple] = set()

    for i, row in enumerate(rows, start=2):  # แถว 1 = Header
        parsed, err = _validate_row(row)
        if err:
            outcomes.append(_RowOutcome(row_no=i, ok=False, message=err, raw_data=_jsonable(row)))
            continue

        key = (
            parsed["department"],
            parsed["budget_type"].value,
            parsed["account_code"],
            parsed["period_start"].isoformat(),
            parsed["period_end"].isoformat(),
        )
        if key in seen_keys:
            outcomes.append(
                _RowOutcome(
                    row_no=i,
                    ok=False,
                    message="ซ้ำกับแถวอื่นในไฟล์เดียวกัน (Department+Type+Code+ช่วงเวลาเดียวกัน)",
                    department=parsed["department"],
                    account_code=parsed["account_code"],
                    raw_data=_jsonable(row),
                )
            )
            continue
        seen_keys.add(key)

        existing = (
            db.execute(
                select(BudgetMaster).where(
                    BudgetMaster.department == parsed["department"],
                    BudgetMaster.budget_type == parsed["budget_type"],
                    BudgetMaster.account_code == parsed["account_code"],
                    BudgetMaster.period_start == parsed["period_start"],
                    BudgetMaster.period_end == parsed["period_end"],
                )
            )
            .scalars()
            .first()
        )

        warning = ""
        overlap = (
            db.execute(
                select(BudgetMaster).where(
                    BudgetMaster.department == parsed["department"],
                    BudgetMaster.budget_type == parsed["budget_type"],
                    BudgetMaster.account_code == parsed["account_code"],
                    BudgetMaster.period_start <= parsed["period_end"],
                    BudgetMaster.period_end >= parsed["period_start"],
                    BudgetMaster.period_start != parsed["period_start"],
                )
            )
            .scalars()
            .first()
        )
        if overlap is not None:
            warning = " (คำเตือน: ช่วงเวลาทับซ้อนกับแถวเดิมที่มีอยู่แล้ว — ตรวจสอบให้แน่ใจว่าตั้งใจ)"

        if existing is not None:
            existing.budgeted_amount = parsed["budgeted_amount"]
            existing.budget_name = parsed["budget_name"]
            outcomes.append(
                _RowOutcome(
                    row_no=i,
                    ok=True,
                    message=f"อัปเดตแถวเดิม (id={existing.id}){warning}",
                    department=parsed["department"],
                    account_code=parsed["account_code"],
                )
            )
        else:
            new_row = BudgetMaster(
                department=parsed["department"],
                budget_type=parsed["budget_type"],
                account_code=parsed["account_code"],
                period_start=parsed["period_start"],
                period_end=parsed["period_end"],
                budget_name=parsed["budget_name"],
                budgeted_amount=parsed["budgeted_amount"],
                used_amount=Decimal("0"),
            )
            db.add(new_row)
            outcomes.append(
                _RowOutcome(
                    row_no=i,
                    ok=True,
                    message=f"เพิ่มแถวใหม่{warning}",
                    department=parsed["department"],
                    account_code=parsed["account_code"],
                )
            )

    success_rows = sum(1 for o in outcomes if o.ok)
    error_rows = sum(1 for o in outcomes if not o.ok)
    batch = BudgetUploadBatch(
        filename=filename,
        uploaded_by_id=uploaded_by_id,
        total_rows=len(outcomes),
        success_rows=success_rows,
        error_rows=error_rows,
    )
    db.add(batch)
    db.flush()

    for o in outcomes:
        if not o.ok:
            db.add(
                BudgetUploadRowError(
                    batch_id=batch.id,
                    row_no=o.row_no,
                    error_message=o.message,
                    raw_data=o.raw_data or None,
                )
            )

    return batch, outcomes


def _jsonable(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, date | datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
