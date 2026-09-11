// PR-Robot — Shared Frontend Helper (Phase 7)
// ไม่ใช้ Framework ภายนอก — Vanilla JS ล้วนตามหลักการ "Web Frontend ขั้นต่ำ"

// Scope Revision (Phase 9, 2026-09-03): เหลือ 2 สถานะ — draft (แก้ไขได้) และ
// finalized (ล็อกแล้ว เปลี่ยนอัตโนมัติตอนกดพิมพ์/ดาวน์โหลด PDF ครั้งแรก)
// Localization Phase 2 (2026-09-11): Badge/Dropdown เป็น English ล้วนตาม Scope ที่
// Confirm ไว้ (จัดกลุ่มเดียวกับปุ่ม/Label — ไม่ใช่ Header ที่ใช้ Bilingual)
const PR_STATUS_LABEL = {
  draft: "Draft (Editable)",
  finalized: "Finalized",
};

// ประเภทเอกสารต้นทาง (Phase 9, 2026-09-03): AI เดาเองจากเนื้อหา ผู้ใช้แก้ไขทีหลังได้
const DOC_TYPE_LABEL = {
  quotation: "Quotation",
  receiving_note: "Receiving Note",
  borrow_note: "Borrow Note",
  delivery_note: "Delivery Note",
  other: "Other",
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
  // แถบบนสุด (Shell Redesign, 2026-09-11) — ชื่อเดียวกับ Sidebar แค่แสดงซ้ำในตำแหน่ง Header
  const topNameEl = document.getElementById("top-header-name");
  if (topNameEl) topNameEl.textContent = me.name;
  // ตัวอักษรย่อในวงกลม Sidebar (2026-09-04 — Design System v2) — เอาแค่ตัวแรกของ
  // แต่ละคำ สูงสุด 2 ตัว เผื่อชื่อเป็นภาษาไทยที่ไม่มีแนวคิด "ตัวพิมพ์ใหญ่" ก็ยังอ่านได้
  const avatarEl = document.getElementById("nav-user-avatar");
  // Avatar ที่แถบบนสุด (Correction 2026-09-11 ตาม Design Mockup ใหม่) ใช้ตัวย่อ
  // เดียวกับ Avatar ที่ Sidebar เป๊ะ เลยคำนวณ initials ครั้งเดียวใช้ร่วมกัน
  const topAvatarEl = document.getElementById("top-header-avatar");
  if ((avatarEl || topAvatarEl) && me.name) {
    const initials = me.name
      .trim()
      .split(/\s+/)
      .map((part) => part[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
    if (avatarEl) avatarEl.textContent = initials;
    if (topAvatarEl) topAvatarEl.textContent = initials;
  }
  // Full RBAC (Correction 2026-09-10) — ทุกเมนูซ่อนเป็น Default ใน base.html (class
  // "hidden") เปิดให้เฉพาะคนมีสิทธิ์ตรงนี้ที่เดียว ดู Docstring app/models/user.py และ
  // app/core/deps.py สำหรับความหมายของแต่ละ Field/เงื่อนไขแต่ละเมนู
  const canViewPr = me.is_admin || me.can_view_pr || me.can_view_all_pr;
  ["nav-pr-list", "nav-pr-new", "nav-doc-upload"].forEach((id) => {
    if (canViewPr) document.getElementById(id)?.classList.remove("hidden");
  });

  const canViewAr = me.is_admin || me.can_view_ar || me.can_view_all_ar;
  const navAr = document.getElementById("nav-ar");
  if (canViewAr) navAr?.classList.remove("hidden");

  const canViewAiUsage = me.is_admin || me.is_fa;
  const navAiUsage = document.getElementById("nav-ai-usage");
  if (canViewAiUsage) navAiUsage?.classList.remove("hidden");

  const canViewBudget = me.is_admin || me.is_fa;
  const navBudget = document.getElementById("nav-budget");
  if (canViewBudget) navBudget?.classList.remove("hidden");

  const navLevels = document.getElementById("nav-budget-levels");
  if (me.is_admin) navLevels?.classList.remove("hidden");

  const navUsers = document.getElementById("nav-users");
  if (me.is_admin) navUsers?.classList.remove("hidden");

  // Log PR / Log AR (Correction 3 — แยก Log ออกเป็น 2 เมนูอิสระ, 2026-09-10)
  const canViewLogPr = me.is_admin || me.can_view_all_pr;
  const navLogPr = document.getElementById("nav-log-pr");
  if (canViewLogPr) navLogPr?.classList.remove("hidden");

  const canViewLogAr = me.is_admin || me.is_fa || me.can_view_all_ar;
  const navLogAr = document.getElementById("nav-log-ar");
  if (canViewLogAr) navLogAr?.classList.remove("hidden");

  // My Approvals (Phase B/2, 2026-09-10; Correction — Full RBAC, 2026-09-10) — เมนู
  // "การอนุมัติของฉัน" โชว์ให้ Admin เสมอ หรือ User ที่ถูก Admin เปิด can_view_approvals
  // ให้จากหน้า "จัดการ User" — ตัด is_fa ออกจากเงื่อนไขนี้แล้ว (FA หมายถึงแค่สิทธิ์ทำ FA
  // Acknowledge เท่านั้น ไม่ได้แปลว่าเห็นเมนูนี้ด้วยอัตโนมัติ — ดู app/core/deps.py)
  const canSeeApprovals = me.is_admin || me.can_view_approvals;
  const navApprovalsToggle = document.getElementById("nav-approvals-toggle");
  if (canSeeApprovals) {
    navApprovalsToggle?.classList.remove("hidden");
    await setupMyApprovalsNav();
  }

  // Shell Redesign (2026-09-11) — Sidebar แบ่งเป็น 3 หมวด (MAIN MENU/APPROVALS/
  // ADMINISTRATION) มีเส้นคั่น+หัวข้อของตัวเอง ต้องซ่อนทั้งหมวดถ้าไม่มีเมนูใดใน
  // หมวดนั้นได้รับสิทธิ์เลย (เช่น User ที่เป็นแค่ FA ล้วนๆ ไม่มีสิทธิ์เมนูใน MAIN MENU)
  // ไม่งั้นจะเห็นหัวข้อคั่นลอยๆ ไม่มีเมนูข้างใต้
  ["nav-section-main", "nav-section-approvals", "nav-section-admin"].forEach((sectionId) => {
    const section = document.getElementById(sectionId);
    if (!section) return;
    const hasVisibleItem = Array.from(section.querySelectorAll(".nav-item")).some(
      (el) => !el.classList.contains("hidden")
    );
    section.classList.toggle("hidden", !hasVisibleItem);
  });

  return me;
}

// My Approvals (Phase B/2, 2026-09-10) — Toggle Accordion + Badge Count + Active Tab
async function setupMyApprovalsNav() {
  const toggle = document.getElementById("nav-approvals-toggle");
  const submenu = document.getElementById("approvals-submenu");
  if (!toggle || !submenu || toggle.dataset.bound) {
    // ยังต้อง Refresh Badge/Active Tab ทุกครั้งแม้ Bind Handler ไปแล้วรอบก่อน (Guard
    // เฉพาะการผูก Event ซ้ำซ้อน ไม่ใช่การโหลดข้อมูล)
  } else {
    toggle.dataset.bound = "1";
    toggle.addEventListener("click", () => {
      toggle.classList.toggle("expanded");
      submenu.classList.toggle("open");
    });
  }

  const onMyApprovalsPage = window.location.pathname.startsWith("/app/my-approvals");
  const currentTab = new URLSearchParams(window.location.search).get("tab");
  submenu.querySelectorAll(".submenu-item").forEach((el) => {
    el.classList.toggle("active", onMyApprovalsPage && el.dataset.tab === currentTab);
  });
  if (onMyApprovalsPage) {
    toggle.classList.add("expanded");
    submenu.classList.add("open");
  }

  try {
    const res = await apiFetch("/ars/my-approvals/counts");
    if (!res.ok) return;
    const counts = await res.json();
    ["waiting", "mine", "history", "returned"].forEach((bucket) => {
      const el = document.getElementById(`badge-${bucket}`);
      if (!el) return;
      const n = counts[bucket] || 0;
      el.textContent = String(n);
      el.classList.toggle("zero", n === 0);
    });
  } catch (e) {
    // เงียบไว้ — Badge เป็นแค่ตัวช่วยแสดงผล ไม่ใช่ข้อมูลสำคัญที่พังแล้ว Block การใช้งานหน้าอื่น
  }
}

// ไฮไลต์เมนู Sidebar ที่ตรงกับหน้าปัจจุบัน (2026-09-04 — Design System v2) — เทียบ
// จาก data-nav-path ที่กำหนดไว้ในแต่ละลิงก์ของ base.html เทียบกับ URL ปัจจุบัน แทนที่
// จะเพิ่มตัวแปรส่งจาก Backend เพื่อไม่ต้องแก้ pages.py เพิ่ม
function markActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll(".sidebar .nav-item").forEach((link) => {
    const navPath = link.dataset.navPath;
    const isActive =
      navPath === path || (navPath !== "/app/" && path.startsWith(navPath));
    link.classList.toggle("active", isActive);
  });
}

function setupLogout() {
  // Comment 2026-09-11 (รอบ 3): มีปุ่ม Logout 2 จุดแล้ว (Sidebar Footer เดิม +
  // เมนู Avatar ที่ Header ใหม่) ใช้ Handler เดียวกันทั้งคู่
  const btns = document.querySelectorAll("#logout-link, #top-logout-link");
  if (!btns.length) return;
  const doLogout = async (e) => {
    e.preventDefault();
    await fetch("/auth/logout", { method: "POST" });
    window.location.href = "/app/login";
  };
  btns.forEach((btn) => btn.addEventListener("click", doLogout));
}

function statusBadge(status) {
  const label = PR_STATUS_LABEL[status] || status;
  return `<span class="badge badge-${status}">${label}</span>`;
}

// Correction 2026-09-10 (Comment 1/2): Badge หัวเรื่อง AR (ar_detail.html/ar_list.html)
// ต้องสัมพันธ์กับสถานะอนุมัติงบจริง ไม่ใช่แค่ draft/finalized เฉยๆ เหมือน PR — ผู้ใช้
// Confirm ตาราง 3 แถว: Draft (ยังแก้ไขได้) / Workflow Running (พิมพ์แล้วแต่ยังอนุมัติไม่
// ครบ) / Approved (อนุมัติครบทุกคนแล้ว ไม่ว่าจะรอ FA หักงบหรือหักงบแล้วก็ถือว่า Approved)
// ใช้ร่วมกันทั้ง ar_detail.html (ar-status-badge) และ ar_list.html (คอลัมน์ Status) —
// รับ ar object เต็ม (ต้องมีทั้ง .status และ .budget_approval_status)
const AR_TOP_STATUS_LABEL = {
  draft: "Draft (Editable)",
  workflow_running: "Workflow Running",
  approved: "Approved",
  rejected: "Rejected",
};

// แยก Logic ตัดสิน Bucket ออกจาก arTopStatusBadge() เป็นฟังก์ชันกลาง (Design Redesign,
// 2026-09-11) — ar_list.html (การ์ดสถิติ/Kanban) ใช้ตัดสิน Bucket แบบเดียวกันนี้ด้วย
// กันตรรกะหลุดไม่ตรงกันระหว่างหน้า Badge เดี่ยวกับ List/Kanban
function arStatusBucket(ar) {
  if (ar.status !== "finalized") return "draft";
  if (ar.budget_approval_status === "rejected") return "rejected";
  if (ar.budget_approval_status === "pending_fa_acknowledge" || ar.budget_approval_status === "approved") {
    return "approved";
  }
  // pending หรือกรณีอื่น (not_submitted ไม่ควรเกิดตอน finalized ตามจริง) — ถือว่ายังรอ
  // อนุมัติอยู่
  return "workflow_running";
}

function arTopStatusBadge(ar) {
  const key = arStatusBucket(ar);
  return `<span class="badge badge-ar-${key}">${AR_TOP_STATUS_LABEL[key]}</span>`;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

// ───────────────────── Attachment Lightbox (Shared, Comment 4 — 2026-09-10) ─────────────
// เดิมมีแค่ในหน้า "การอนุมัติของฉัน" (ar_my_approvals.html) — ผู้ใช้แจ้งว่าอยากให้เอกสาร
// แนบในหน้า "รายละเอียด AR" (ar_detail.html) คลิกแล้ว Float Preview เหมือนกัน จึงย้าย
// เครื่องยนต์ Lightbox มาไว้ในนี้เป็นฟังก์ชันกลาง เรียกใช้ผ่าน
// openAttachmentLightbox(arId, attachments, index) — attachments คือ Array ของ
// ARAttachmentRead ที่โหลดมาแล้ว (ต้องมี id/file_name/content_type/file_size) DOM ของ
// Lightbox เองถูกสร้างแบบ Lazy (ensureLightboxDom) ตอนเปิดครั้งแรกเท่านั้น ไม่ต้องประกาศ
// Markup ซ้ำในทุกหน้าที่ใช้
let LIGHTBOX_AR_ID = null;
let LIGHTBOX_ATTACHMENTS = [];
let LIGHTBOX_ZOOM = 100;

function fmtFileSizeLightbox(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isXlsxAttachment(att) {
  const ct = att.content_type || "";
  const name = (att.file_name || "").toLowerCase();
  return (
    ct.includes("spreadsheetml") || ct === "application/vnd.ms-excel" || name.endsWith(".xlsx") || name.endsWith(".xls")
  );
}

function ensureLightboxDom() {
  if (document.getElementById("shared-lightbox-overlay")) return;
  const wrap = document.createElement("div");
  wrap.innerHTML = `<div class="overlay ma-lightbox-overlay" id="shared-lightbox-overlay">
    <div class="ma-lightbox">
      <div class="ma-lightbox-head">
        <div class="ma-lightbox-tabs" id="shared-lightbox-tabs"></div>
        <div class="ma-lightbox-tools">
          <span class="ma-lightbox-zoom-group" id="shared-lightbox-zoom-group">
            <button type="button" class="secondary" id="shared-lightbox-zoom-out">−</button>
            <span class="mono" id="shared-lightbox-zoom-level">100%</span>
            <button type="button" class="secondary" id="shared-lightbox-zoom-in">+</button>
          </span>
          <button type="button" class="ma-popup-close" id="shared-lightbox-close">✕</button>
        </div>
      </div>
      <div class="ma-lightbox-body" id="shared-lightbox-body"></div>
    </div>
  </div>`;
  document.body.appendChild(wrap.firstElementChild);

  document.getElementById("shared-lightbox-close").addEventListener("click", closeAttachmentLightbox);
  document.getElementById("shared-lightbox-overlay").addEventListener("click", (e) => {
    if (e.target.id === "shared-lightbox-overlay") closeAttachmentLightbox();
  });
  document.getElementById("shared-lightbox-zoom-in").addEventListener("click", () => {
    LIGHTBOX_ZOOM = Math.min(LIGHTBOX_ZOOM + 25, 300);
    applyLightboxZoom();
  });
  document.getElementById("shared-lightbox-zoom-out").addEventListener("click", () => {
    LIGHTBOX_ZOOM = Math.max(LIGHTBOX_ZOOM - 25, 25);
    applyLightboxZoom();
  });
}

function applyLightboxZoom() {
  document.getElementById("shared-lightbox-zoom-level").textContent = `${LIGHTBOX_ZOOM}%`;
  const img = document.getElementById("shared-lightbox-img");
  if (img) img.style.transform = `scale(${LIGHTBOX_ZOOM / 100})`;
}

function escapeHtmlCell(v) {
  if (v === null || v === undefined || v === "") return "";
  return escapeHtml(String(v));
}

// แก้ไขเพิ่ม (2026-09-10): เดิม Preview แค่ Sheet แรกของไฟล์ Excel — ผู้ใช้แจ้งว่าไฟล์
// จริงมีหลาย Tab (Sheet) ต้องเห็นครบทุก Tab ไม่ใช่แค่ Tab แรก จึง Render เป็น Sub-tab ให้
// สลับดูแต่ละ Sheet ได้ (Backend ส่งกลับทุก Sheet มาแล้ว — ดู xlsx-preview endpoint)
function xlsxSheetTableHtml(sheet) {
  if (sheet.rows.length === 0) {
    return '<p class="muted">Sheet นี้ไม่มีข้อมูล</p>';
  }
  const tableRows = sheet.rows
    .map(
      (row, i) =>
        `<tr>${row.map((cell) => (i === 0 ? `<th>${escapeHtmlCell(cell)}</th>` : `<td>${escapeHtmlCell(cell)}</td>`)).join("")}</tr>`
    )
    .join("");
  const truncatedNote = sheet.truncated
    ? '<div class="ma-xlsx-truncated-note">แสดงบางส่วน — ดาวน์โหลดเพื่อดูฉบับเต็ม</div>'
    : "";
  return `${truncatedNote}<div class="ma-xlsx-table-wrap"><table class="ma-xlsx-table">${tableRows}</table></div>`;
}

async function renderXlsxAttachmentPreview(att, body, url) {
  const res = await apiFetch(`/ars/${LIGHTBOX_AR_ID}/attachments/${att.id}/xlsx-preview`);
  if (!res.ok) {
    body.innerHTML = `<p class="muted">ไม่สามารถ Preview ไฟล์ Excel นี้ได้ (รองรับเฉพาะ .xlsx)<br><a href="${url}" target="_blank">ดาวน์โหลด ${escapeHtml(att.file_name)} (${fmtFileSizeLightbox(att.file_size)})</a></p>`;
    return;
  }
  const data = await res.json();
  const sheets = data.sheets || [];
  if (sheets.length === 0) {
    body.innerHTML = '<p class="muted">ไฟล์ Excel นี้ไม่มี Sheet</p>';
    return;
  }
  body.innerHTML = `
    <div class="ma-xlsx-preview">
      <div class="ma-xlsx-sheet-tabs" id="ma-xlsx-sheet-tabs"></div>
      <div class="ma-xlsx-sheet-body" id="ma-xlsx-sheet-body"></div>
    </div>`;
  const tabsEl = body.querySelector("#ma-xlsx-sheet-tabs");
  const sheetBodyEl = body.querySelector("#ma-xlsx-sheet-body");
  tabsEl.innerHTML = sheets
    .map((s, i) => `<button type="button" class="ma-xlsx-sheet-tab ${i === 0 ? "active" : ""}" data-index="${i}">${escapeHtml(s.sheet_name)}</button>`)
    .join("");
  tabsEl.querySelectorAll(".ma-xlsx-sheet-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      tabsEl.querySelectorAll(".ma-xlsx-sheet-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      sheetBodyEl.innerHTML = xlsxSheetTableHtml(sheets[Number(btn.dataset.index)]);
    });
  });
  sheetBodyEl.innerHTML = xlsxSheetTableHtml(sheets[0]);
}

async function renderAttachmentLightboxDoc(att) {
  LIGHTBOX_ZOOM = 100;
  const body = document.getElementById("shared-lightbox-body");
  const url = `/ars/${LIGHTBOX_AR_ID}/attachments/${att.id}/download`;
  const ct = att.content_type || "";
  const isImage = ct.startsWith("image/");
  document.getElementById("shared-lightbox-zoom-group").classList.toggle("hidden", !isImage);

  const activeIndex = LIGHTBOX_ATTACHMENTS.indexOf(att);
  document.getElementById("shared-lightbox-tabs").querySelectorAll(".ma-lightbox-tab").forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.index) === activeIndex);
  });

  if (ct === "application/pdf") {
    body.innerHTML = `<iframe src="${url}"></iframe>`;
  } else if (isImage) {
    body.innerHTML = `<img id="shared-lightbox-img" src="${url}" alt="${escapeHtml(att.file_name)}">`;
  } else if (isXlsxAttachment(att)) {
    body.innerHTML = '<p class="muted">กำลังโหลด Preview...</p>';
    await renderXlsxAttachmentPreview(att, body, url);
  } else {
    body.innerHTML = `<p class="muted">ไม่รองรับ Preview ไฟล์ประเภทนี้ในเบราว์เซอร์<br><a href="${url}" target="_blank">ดาวน์โหลด ${escapeHtml(att.file_name)} (${fmtFileSizeLightbox(att.file_size)})</a></p>`;
  }
  applyLightboxZoom();
}

function openAttachmentLightbox(arId, attachments, index) {
  ensureLightboxDom();
  LIGHTBOX_AR_ID = arId;
  LIGHTBOX_ATTACHMENTS = attachments;
  const tabsEl = document.getElementById("shared-lightbox-tabs");
  tabsEl.innerHTML = attachments
    .map((a, i) => `<button type="button" class="ma-lightbox-tab" data-index="${i}">${escapeHtml(a.file_name)}</button>`)
    .join("");
  tabsEl.querySelectorAll(".ma-lightbox-tab").forEach((btn) => {
    btn.addEventListener("click", () => renderAttachmentLightboxDoc(LIGHTBOX_ATTACHMENTS[Number(btn.dataset.index)]));
  });
  renderAttachmentLightboxDoc(attachments[index]);
  document.getElementById("shared-lightbox-overlay").classList.add("open");
}

function closeAttachmentLightbox() {
  const overlay = document.getElementById("shared-lightbox-overlay");
  if (overlay) overlay.classList.remove("open");
  const body = document.getElementById("shared-lightbox-body");
  if (body) body.innerHTML = "";
}

// แสดงวันที่แบบ dd/mm/yyyy เสมอ (Feedback จริงจากผู้ใช้ 2026-09-03) — รับ Input เป็น
// "yyyy-mm-dd" (จาก API) หรือ ISO Datetime เต็มก็ได้ ใช้แค่แสดงผลเท่านั้น
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

// Custom Date Field แบบ dd/mm/yyyy (Feedback จริงจากผู้ใช้ 2026-09-03) — Native
// <input type=date> แสดงผล/ปฏิทินตาม Locale ของเบราว์เซอร์/OS ผู้ใช้เอง บังคับให้เป็น
// dd/mm/yyyy ข้าม Browser ไม่ได้จริงๆ ทำ Widget เองแบบ Vanilla JS แทน (ไม่พึ่ง Library
// ภายนอกตามหลักการเดิมของโปรเจกต์) — ช่อง Input เป็น Readonly กดแล้วเปิดปฏิทินให้เลือก
// เท่านั้น (กันพิมพ์ผิดรูปแบบ/วันที่ไม่มีจริง) ค่าจริงเก็บเป็น yyyy-mm-dd ใน data-iso
// เสมอ ใช้ getDateFieldIso()/setDateFieldIso() อ่าน-เขียนแทนการยุ่งกับ .value ตรงๆ

function dateFieldHtml(extraClass, isoValue, ariaLabel) {
  const display = formatDateDMY(isoValue) || "";
  const ariaAttr = ariaLabel ? ` aria-label="${ariaLabel}"` : "";
  return `<input type="text" class="date-field ${extraClass || ""}" data-iso="${isoValue || ""}" value="${display}" placeholder="dd/mm/yyyy" readonly autocomplete="off"${ariaAttr}>`;
}

function getDateFieldIso(el) {
  return el ? el.dataset.iso || "" : "";
}

function setDateFieldIso(el, iso) {
  if (!el) return;
  el.dataset.iso = iso || "";
  el.value = formatDateDMY(iso) || "";
}

let _activeDatePopup = null;

function closeDatePopup() {
  if (_activeDatePopup) {
    _activeDatePopup.el.remove();
    document.removeEventListener("click", _activeDatePopup.onDocClick, true);
    _activeDatePopup = null;
  }
}

function openDatePopup(inputEl) {
  if (_activeDatePopup && _activeDatePopup.inputEl === inputEl) {
    closeDatePopup();
    return;
  }
  closeDatePopup();

  const iso = inputEl.dataset.iso;
  let view = iso ? new Date(`${iso}T00:00:00`) : new Date();
  if (Number.isNaN(view.getTime())) view = new Date();
  let viewYear = view.getFullYear();
  let viewMonth = view.getMonth(); // 0-11

  const popup = document.createElement("div");
  popup.className = "date-popup";

  function render() {
    const monthNames = [
      "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
      "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
    ];
    const first = new Date(viewYear, viewMonth, 1);
    const startDow = first.getDay(); // 0=Sun
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const todayIso = new Date().toISOString().slice(0, 10);
    let cells = "";
    for (let i = 0; i < startDow; i++) cells += `<span class="date-popup-cell date-popup-empty"></span>`;
    for (let d = 1; d <= daysInMonth; d++) {
      const cellIso = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const cls = ["date-popup-cell"];
      if (cellIso === iso) cls.push("date-popup-selected");
      if (cellIso === todayIso) cls.push("date-popup-today");
      cells += `<button type="button" class="${cls.join(" ")}" data-iso="${cellIso}">${d}</button>`;
    }
    popup.innerHTML = `
      <div class="date-popup-header">
        <button type="button" class="date-popup-nav" data-nav="-1">‹</button>
        <span>${monthNames[viewMonth]} ${viewYear}</span>
        <button type="button" class="date-popup-nav" data-nav="1">›</button>
      </div>
      <div class="date-popup-grid date-popup-dow">
        <span>อา</span><span>จ</span><span>อ</span><span>พ</span><span>พฤ</span><span>ศ</span><span>ส</span>
      </div>
      <div class="date-popup-grid">${cells}</div>
      <div class="date-popup-footer">
        <button type="button" class="date-popup-clear">ล้างวันที่</button>
      </div>
    `;
    popup.querySelectorAll(".date-popup-nav").forEach((btn) => {
      btn.addEventListener("click", () => {
        viewMonth += Number(btn.dataset.nav);
        if (viewMonth < 0) {
          viewMonth = 11;
          viewYear -= 1;
        }
        if (viewMonth > 11) {
          viewMonth = 0;
          viewYear += 1;
        }
        render();
      });
    });
    popup.querySelectorAll(".date-popup-cell:not(.date-popup-empty)").forEach((cell) => {
      cell.addEventListener("click", () => {
        setDateFieldIso(inputEl, cell.dataset.iso);
        inputEl.dispatchEvent(new Event("change", { bubbles: true }));
        closeDatePopup();
      });
    });
    popup.querySelector(".date-popup-clear").addEventListener("click", () => {
      setDateFieldIso(inputEl, "");
      inputEl.dispatchEvent(new Event("change", { bubbles: true }));
      closeDatePopup();
    });
  }
  render();

  document.body.appendChild(popup);
  const rect = inputEl.getBoundingClientRect();
  popup.style.position = "absolute";
  popup.style.top = `${window.scrollY + rect.bottom + 4}px`;
  popup.style.left = `${window.scrollX + rect.left}px`;

  // ปิด Popup เมื่อคลิกนอกกล่อง (Capture Phase กันชนกับ Event Delegation อื่นบนหน้า)
  const onDocClick = (e) => {
    if (!popup.contains(e.target) && e.target !== inputEl) closeDatePopup();
  };
  setTimeout(() => document.addEventListener("click", onDocClick, true), 0);

  _activeDatePopup = { el: popup, inputEl, onDocClick };
}

function bindDateFieldsIn(root) {
  (root || document).querySelectorAll(".date-field").forEach((el) => {
    if (el.dataset.dateBound) return;
    el.dataset.dateBound = "1";
    el.addEventListener("click", () => openDatePopup(el));
  });
}

// เปลี่ยนรหัสผ่านของตัวเอง (Popup ที่ Sidebar, 2026-09-11) — คลิกชื่อ/Avatar เปิดเมนู
// เล็กๆ มีตัวเลือก "Change Password" เดียว กด Logout แยกจากเมนูนี้ (ยังเป็น Icon เดิม
// ข้างๆ ไม่ต้องเปิดเมนูก่อน)
function setupChangePassword() {
  const trigger = document.getElementById("sidebar-user-trigger");
  const menu = document.getElementById("sidebar-user-menu");
  const openBtn = document.getElementById("open-change-password");
  const modal = document.getElementById("change-password-modal");
  const errorEl = document.getElementById("cp-error");
  const currentEl = document.getElementById("cp-current");
  const newEl = document.getElementById("cp-new");
  const confirmEl = document.getElementById("cp-confirm");
  const saveBtn = document.getElementById("cp-save");
  const cancelBtn = document.getElementById("cp-cancel");
  // Comment 2026-09-11 (รอบ 3): Avatar ที่ Header ก็ต้องเปิดเมนูนี้ได้เหมือนกัน
  // ใช้ Modal เดียวกัน (change-password-modal) ไม่ได้สร้างซ้ำ
  const topTrigger = document.getElementById("top-header-avatar-trigger");
  const topMenu = document.getElementById("top-header-user-menu");
  const topOpenBtn = document.getElementById("top-open-change-password");
  if (!trigger || !menu || !modal) return;

  const closeMenu = () => menu.classList.add("hidden");
  const closeTopMenu = () => topMenu?.classList.add("hidden");
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    closeTopMenu();
    menu.classList.toggle("hidden");
  });
  topTrigger?.addEventListener("click", (e) => {
    e.stopPropagation();
    closeMenu();
    topMenu.classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    if (!menu.classList.contains("hidden") && !menu.contains(e.target) && e.target !== trigger) {
      closeMenu();
    }
    if (topMenu && !topMenu.classList.contains("hidden") && !topMenu.contains(e.target) && e.target !== topTrigger) {
      closeTopMenu();
    }
  });

  const resetForm = () => {
    currentEl.value = "";
    newEl.value = "";
    confirmEl.value = "";
    errorEl.classList.add("hidden");
    errorEl.textContent = "";
  };
  const openModal = () => {
    resetForm();
    modal.classList.remove("hidden");
    closeMenu();
    closeTopMenu();
  };
  const closeModal = () => modal.classList.add("hidden");

  openBtn?.addEventListener("click", openModal);
  topOpenBtn?.addEventListener("click", openModal);
  cancelBtn?.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  saveBtn?.addEventListener("click", async () => {
    errorEl.classList.add("hidden");
    if (newEl.value.length < 8) {
      errorEl.textContent = "รหัสผ่านใหม่ต้องมีอย่างน้อย 8 ตัวอักษร";
      errorEl.classList.remove("hidden");
      return;
    }
    if (newEl.value !== confirmEl.value) {
      errorEl.textContent = "รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน";
      errorEl.classList.remove("hidden");
      return;
    }
    saveBtn.disabled = true;
    const res = await apiFetch("/auth/password", {
      method: "PATCH",
      body: JSON.stringify({ current_password: currentEl.value, new_password: newEl.value }),
    });
    saveBtn.disabled = false;
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      errorEl.textContent = body.detail || "เปลี่ยนรหัสผ่านไม่สำเร็จ";
      errorEl.classList.remove("hidden");
      return;
    }
    closeModal();
    alert("เปลี่ยนรหัสผ่านสำเร็จ");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupLogout();
  markActiveNav();
  setupChangePassword();
});
