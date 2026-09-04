"""Import ทุก Model ที่นี่ ให้ Base.metadata เห็นครบสำหรับ Alembic"""
from app.models.ai_usage_log import AiUsageLog
from app.models.audit_log import AuditLog
from app.models.pr_number_counter import PRNumberCounter
from app.models.purchasing_requisition import (
    PRBudgetControl,
    PRItem,
    PRStatus,
    PurchasingRequisition,
)
from app.models.source_document import SourceDocType, SourceDocument
from app.models.user import User

__all__ = [
    "AiUsageLog",
    "AuditLog",
    "PRBudgetControl",
    "PRItem",
    "PRNumberCounter",
    "PRStatus",
    "PurchasingRequisition",
    "SourceDocType",
    "SourceDocument",
    "User",
]
