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
  // ตัวอักษรย่อในวงกลม Sidebar (2026-09-04 — Design System v2) — เอาแค่ตัวแรกของ
  // แต่ละคำ สูงสุด 2 ตัว เผื่อชื่อเป็นภาษาไทยที่ไม่มีแนวคิด "ตัวพิมพ์ใหญ่" ก็ยังอ่านได้
  const avatarEl = document.getElementById("nav-user-avatar");
  if (avatarEl && me.name) {
    const initials = me.name
      .trim()
      .split(/\s+/)
      .map((part) => part[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
    avatarEl.textContent = initials;
  }
  // Budget Control (2026-09-09) — เมนู "จัดการ User" (Admin เท่านั้น) / "Level อนุมัติ"
  // (Admin เท่านั้น) / "Budget Control" (FA หรือ Admin) โชว์เฉพาะคนมีสิทธิ์
  const navUsers = document.getElementById("nav-users");
  if (navUsers && me.is_admin) navUsers.classList.remove("hidden");
  const navLevels = document.getElementById("nav-budget-levels");
  if (navLevels && me.is_admin) navLevels.classList.remove("hidden");
  const navBudget = document.getElementById("nav-budget");
  if (navBudget && (me.is_admin || me.is_fa)) navBudget.classList.remove("hidden");
  return me;
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

function dateFieldHtml(extraClass, isoValue) {
  const display = formatDateDMY(isoValue) || "";
  return `<input type="text" class="date-field ${extraClass || ""}" data-iso="${isoValue || ""}" value="${display}" placeholder="dd/mm/yyyy" readonly autocomplete="off">`;
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

document.addEventListener("DOMContentLoaded", () => {
  setupLogout();
  markActiveNav();
});
