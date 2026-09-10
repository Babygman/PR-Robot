"""หน้าเว็บ (Server-rendered Shell) — Phase 7

ทุกหน้าที่นี่คืนแค่ HTML Shell + JS ฝังไว้ (Vanilla JS ไม่มี Framework) ข้อมูลจริงทั้งหมด
โหลดผ่าน Fetch ไปยัง JSON API ที่มีอยู่แล้ว (Phase 3-6) จาก Browser โดยตรง — ไม่ผ่าน
get_current_user ที่นี่เลย (ไม่ Enforce Login ระดับ Route) เพราะ Auth ทำฝั่ง Client:
เรียก GET /auth/me ตอนโหลดหน้า ถ้า 401 จะเด้งไป /app/login เอง (ดู static/app.js)
เหตุผล: ทำให้ Page Route ง่ายมาก ไม่ต้อง Duplicate Logic ตรวจสิทธิ์ระหว่าง Server/Client

Namespace อยู่ใต้ /app ทั้งหมดเพื่อไม่ให้ชนกับ JSON API เดิม (เช่น /prs/{id} ของ API
กับ /app/prs/{id} ของหน้าเว็บ เป็นคนละ Path กันชัดเจน)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"

router = APIRouter(prefix="/app", tags=["pages"])
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


@router.get("/login")
def page_login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.get("/")
def page_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={})


@router.get("/prs/new")
def page_pr_new(request: Request):
    return templates.TemplateResponse(request=request, name="pr_edit.html", context={"pr_id": None})


@router.get("/prs/{pr_id}/edit")
def page_pr_edit(request: Request, pr_id: int):
    return templates.TemplateResponse(
        request=request, name="pr_edit.html", context={"pr_id": pr_id}
    )


@router.get("/prs/{pr_id}")
def page_pr_detail(request: Request, pr_id: int):
    return templates.TemplateResponse(
        request=request, name="pr_detail.html", context={"pr_id": pr_id}
    )


@router.get("/ars/new")
def page_ar_new(request: Request):
    return templates.TemplateResponse(request=request, name="ar_edit.html", context={"ar_id": None})


@router.get("/ars/{ar_id}/edit")
def page_ar_edit(request: Request, ar_id: int):
    return templates.TemplateResponse(
        request=request, name="ar_edit.html", context={"ar_id": ar_id}
    )


@router.get("/ars/{ar_id}")
def page_ar_detail(request: Request, ar_id: int):
    return templates.TemplateResponse(
        request=request, name="ar_detail.html", context={"ar_id": ar_id}
    )


@router.get("/ars")
def page_ar_list(request: Request):
    return templates.TemplateResponse(request=request, name="ar_list.html", context={})


@router.get("/documents/upload")
def page_upload(request: Request):
    return templates.TemplateResponse(request=request, name="upload.html", context={})


# My Approvals (Phase B/2, 2026-09-10)
@router.get("/my-approvals")
def page_my_approvals(request: Request):
    return templates.TemplateResponse(request=request, name="ar_my_approvals.html", context={})


@router.get("/ai-usage")
def page_ai_usage(request: Request):
    return templates.TemplateResponse(request=request, name="ai_usage.html", context={})


# Log (Full RBAC, 2026-09-10)
@router.get("/log")
def page_audit_log(request: Request):
    return templates.TemplateResponse(request=request, name="audit_log.html", context={})


# ───────────────────────── Budget Control (Phase 10, 2026-09-09) ─────────────────────────
@router.get("/users")
def page_users(request: Request):
    return templates.TemplateResponse(request=request, name="users.html", context={})


@router.get("/budget-levels")
def page_budget_levels(request: Request):
    return templates.TemplateResponse(request=request, name="budget_levels.html", context={})


@router.get("/budget")
def page_budget(request: Request):
    return templates.TemplateResponse(request=request, name="budget_upload.html", context={})
