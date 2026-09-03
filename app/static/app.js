// PR-Robot — Shared Frontend Helper (Phase 7)
// ไม่ใช้ Framework ภายนอก — Vanilla JS ล้วนตามหลักการ "Web Frontend ขั้นต่ำ"

// Scope Revision (Phase 9, 2026-09-03): เหลือ 2 สถานะ — draft (แก้ไขได้) และ
// finalized (ล็อกแล้ว เปลี่ยนอัตโนมัติตอนกดพิมพ์/ดาวน์โหลด PDF ครั้งแรก)
const PR_STATUS_LABEL = {
  draft: "Draft (แก้ไขได้)",
  finalized: "Finalized (สรุปแล้ว)",
};

// ประเภทเอกสารต้นทาง (Phase 9, 2026-09-03): AI เดาเองจากเนื้อหา ผู้ใช้แก้ไขทีหลังได้
const DOC_TYPE_LABEL = {
  quotation: "ใบเสนอราคา",
  receiving_note: "ใบรับของ",
  borrow_note: "ใบยืมสินค้า",
  delivery_note: "ใบส่งสินค้า",
  other: "อื่นๆ",
};

/**
 * เรียก API ภายใน (Same-Origin) — Cookie แนบให้อัตโนมัติเพราะเป็น Same-Origin เสมอ
 * ถ้าเจอ 401 (ยังไม่ได้ Login/Session หมดอายุ) จะเด้งไปหน้า Login ให้อัตโนมัติ
 */
async function apiFetch(path, options = {}) {
  const opts = { ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  }
  const res = await fetch(path, opts);
  if (res.status === 401) {
    window.location.href = "/app/login?next=" + encodeURIComponent(window.location.pathname);
    throw new Error("ยังไม่ได้ Login");
  }
  return res;
}

async function requireLogin() {
  const res = await apiFetch("/auth/me");
  if (!res.ok) {
    window.location.href = "/app/login";
    return null;
  }
  const me = await res.json();
  const nameEl = document.getElementById("nav-user-name");
  if (nameEl) nameEl.textContent = me.name;
  return me;
}

function setupLogout() {
  const btn = document.getElementById("logout-link");
  if (!btn) return;
  btn.addEventListener("click", async (e) => {
    e.preventDefault();
    await fetch("/auth/logout", { method: "POST" });
    window.location.href = "/app/login";
  });
}

function statusBadge(status) {
  const label = PR_STATUS_LABEL[status] || status;
  return `<span class="badge badge-${status}">${label}</span>`;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

// แสดงวันที่แบบ dd/mm/yyyy เสมอ (Feedback จริงจากผู้ใช้ 2026-09-03) — รับ Input เป็น
// "yyyy-mm-dd" (จาก <input type=date> / API) หรือ ISO Datetime เต็มก็ได้ ใช้แค่แสดงผล
// เท่านั้น ค่าที่ผูกกับ <input type=date> ยังคงเป็น yyyy-mm-dd ตาม HTML Spec เหมือนเดิม
function formatDateDMY(value) {
  if (!value) return "";
  const datePart = String(value).slice(0, 10);
  const m = datePart.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return escapeHtml(value);
  return `${m[3]}/${m[2]}/${m[1]}`;
}

// แสดงวันที่+เวลาแบบ dd/mm/yyyy HH:MM (สำหรับ Timestamp เต็ม เช่น ประวัติ/Audit Log)
function formatDateTimeDMY(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return escapeHtml(value);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

document.addEventListener("DOMContentLoaded", setupLogout);
