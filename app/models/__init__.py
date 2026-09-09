"""Import ทุก Model ที่นี่ ให้ Base.metadata เห็นครบสำหรับ Alembic"""
from app.models.ai_usage_log import AiUsageLog
from app.models.approval_request import (
    ApprovalRequest,
    ARAmountItem,
    ARBudgetApprovalStatus,
    ARBudgetType,
    ARStatus,
)
from app.models.ar_number_counter import ARNumberCounter
from app.models.audit_log import AuditLog
from app.models.budget import (
    ARBudgetApproval,
    BudgetApprovalAction,
    BudgetApprovalLevel,
    BudgetApprovalStepType,
    BudgetMaster,
    BudgetUploadBatch,
    BudgetUploadRowError,
)
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
    "ARAmountItem",
    "ARBudgetApproval",
    "ARBudgetApprovalStatus",
    "ARBudgetType",
    "ARNumberCounter",
    "ARStatus",
    "ApprovalRequest",
    "AuditLog",
    "BudgetApprovalAction",
    "BudgetApprovalLevel",
    "BudgetApprovalStepType",
    "BudgetMaster",
    "BudgetUploadBatch",
    "BudgetUploadRowError",
    "PRBudgetControl",
    "PRItem",
    "PRNumberCounter",
    "PRStatus",
    "PurchasingRequisition",
    "SourceDocType",
    "SourceDocument",
    "User",
]
