import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

const ACCOUNT_NUMBER = 2;
const ACCOUNT_NAME = "giakhanhdoxe";
const TOKEN_FILE = process.env.NBL_API_TOKEN_FILE || "/mnt/c/Users/ADMIN/AppData/Local/NBL_LIVE_2/local_api_token.txt";
const TERMINAL = new Set(["finished", "cancelled", "skipped", "failed", "manual_stop"]);
const MAX_BATCH = 30;

function windowsHost() {
  if (process.env.NBL_API_HOST?.trim()) return process.env.NBL_API_HOST.trim();
  try {
    const text = execFileSync("ip", ["route", "show", "default"], { encoding: "utf8", timeout: 3000 });
    const parts = text.trim().split(/\s+/);
    const i = parts.indexOf("via");
    if (i >= 0 && parts[i + 1]) return parts[i + 1];
  } catch {}
  return "127.0.0.1";
}

function apiBase() {
  return (process.env.NBL_API_URL || `http://${windowsHost()}:${process.env.NBL_API_PORT || "8766"}`).replace(/\/$/, "");
}

function token() {
  const direct = process.env.NBL_API_TOKEN?.trim();
  if (direct) return direct;
  return readFileSync(TOKEN_FILE, "ascii").trim();
}

async function callApi(path, method = "GET", body) {
  const response = await fetch(apiBase() + path, {
    method,
    headers: {
      Authorization: `Bearer ${token()}`,
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(20000),
  });
  let value;
  try { value = await response.json(); }
  catch { value = { ok: false, error: `HTTP ${response.status}` }; }
  if (!response.ok || !value?.ok) throw new Error(String(value?.error || `HTTP ${response.status}`));
  return value.data;
}

function parseDate(raw) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(raw.trim());
  if (!m) return null;
  const d = Number(m[1]), mo = Number(m[2]), y = Number(m[3]);
  if (d < 1 || d > 31 || mo < 1 || mo > 12 || y < 2020 || y > 2100) return null;
  return { d, m: mo, y, iso: `${String(y).padStart(4,"0")}-${String(mo).padStart(2,"0")}-${String(d).padStart(2,"0")}` };
}

function parseTime(raw) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(raw.trim());
  if (!m) return null;
  const h = Number(m[1]), min = Number(m[2]);
  if (h < 0 || h > 23 || min < 0 || min > 59) return null;
  return `${String(h).padStart(2,"0")}:${String(min).padStart(2,"0")}`;
}

function epoch(dateIso, timeText) {
  return Date.parse(`${dateIso}T${timeText}:00+07:00`) / 1000;
}

function fmt(ts) {
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(Number(ts) * 1000));
}

function helpText() {
  return [
    "NBL Direct — lenh Viet khong dau, khong dung AI/quota:",
    "/trangthai — xem ket noi Studio va LIVE hien tai",
    "/lich — xem lich LIVE",
    "/taolich DD/MM/YYYY HH:MM-HH:MM BO;HH:MM-HH:MM BO",
    "Cung ngay: /taolich 25/10/2026 17:45-18:45 1;19:45-20:45 1",
    "Nhieu ngay: /taolich 25/10/2026 17:45-18:45 1;26/10/2026 19:45-20:45 2",
    "/huylich JOB_ID — huy lich chua chay",
    "/dunglive JOB_ID — dung lich dang chay",
    "/huongdan — xem huong dan nay",
    "Lenh cu /nbl_* van dung duoc.",
  ].join("\n");
}

function parseBatch(raw) {
  const chunks = String(raw || "").trim().split(/[;\n]+/).map((s) => s.trim()).filter(Boolean);
  if (!chunks.length) return { error: "Khong co lich de tao." };
  if (chunks.length > MAX_BATCH) return { error: `Moi lan toi da ${MAX_BATCH} lich.` };

  const items = [];
  let currentDate = null;
  for (const chunk of chunks) {
    let rest = chunk;
    const dateMatch = /^(\d{1,2}\/\d{1,2}\/\d{4})\s+(.+)$/.exec(rest);
    if (dateMatch) {
      currentDate = parseDate(dateMatch[1]);
      if (!currentDate) return { error: `Sai ngay: ${dateMatch[1]}` };
      rest = dateMatch[2].trim();
    }
    if (!currentDate) return { error: "Lich dau tien phai co ngay DD/MM/YYYY." };

    const m = /^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})(?:\s+(\d{1,3}))?$/.exec(rest);
    if (!m) {
      items.push({ invalid: true, raw: chunk, reason: "cu phap sai" });
      continue;
    }
    const st = parseTime(m[1]), en = parseTime(m[2]);
    const bundle = m[3] === undefined ? 1 : Number(m[3]);
    if (!st || !en || !Number.isInteger(bundle) || bundle < 0 || bundle > 200) {
      items.push({ invalid: true, raw: chunk, reason: "gio/bo khong hop le" });
      continue;
    }
    items.push({ date: { ...currentDate }, st, en, bundle, raw: chunk });
  }
  return { items };
}

async function statusHandler() {
  try {
    const [accounts, live] = await Promise.all([callApi("/api/accounts"), callApi("/api/live/status")]);
    const a = (accounts || []).find((x) => Number(x.account_number ?? x.number) === ACCOUNT_NUMBER || x.account === ACCOUNT_NAME);
    if (!a) return { text: `Khong tim thay nick ${ACCOUNT_NAME}.` };
    return { text: [
      `✅ ${ACCOUNT_NAME} · nick so ${ACCOUNT_NUMBER}`,
      `Studio: ${a.studio_connected ? "da ket noi" : "chua ket noi"}`,
      `Playlist: ${a.playlist_count ?? 0}`,
      `LIVE dang hoat dong: ${live?.count ?? 0}`,
    ].join("\n") };
  } catch (e) { return { text: `❌ NBL API: ${e?.message || String(e)}` }; }
}

async function schedulesHandler() {
  try {
    const rows = (await callApi("/api/schedules")) || [];
    const mine = rows.filter((x) => Number(x.account_number) === ACCOUNT_NUMBER);
    if (!mine.length) return { text: `Nick ${ACCOUNT_NAME}: chua co lich.` };
    const active = mine.filter((x) => !TERMINAL.has(String(x.state)));
    const show = (active.length ? active : mine.slice(-10)).slice(0, 20);
    return { text: `${ACCOUNT_NAME} · ${mine.length} lich (${active.length} chua ket thuc)\n` + show.map((x) => `${fmt(x.start)} → ${new Intl.DateTimeFormat("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(Number(x.end) * 1000))} · bo ${x.bundle_index ?? 0} · ${x.state} · ${String(x.id).slice(0, 8)}`).join("\n") };
  } catch (e) { return { text: `❌ NBL API: ${e?.message || String(e)}` }; }
}

async function createHandler(ctx) {
  const parsed = parseBatch(ctx.args);
  if (parsed.error) return { text: `${parsed.error}\n\n${helpText()}` };

  let existing;
  try { existing = (await callApi("/api/schedules")) || []; }
  catch (e) { return { text: `❌ Khong doc duoc lich truoc khi tao: ${e?.message || String(e)}` }; }

  const reserved = existing
    .filter((x) => Number(x.account_number) === ACCOUNT_NUMBER && !TERMINAL.has(String(x.state)))
    .map((x) => ({ start: Number(x.start), end: Number(x.end), id: String(x.id || "") }));
  const results = [];
  let okCount = 0;

  for (const item of parsed.items) {
    if (item.invalid) {
      results.push(`❌ ${item.raw}: ${item.reason}`);
      continue;
    }
    const { date, st, en, bundle, raw } = item;
    const start = epoch(date.iso, st), end = epoch(date.iso, en);
    if (!(end > start)) { results.push(`❌ ${raw}: gio ket thuc phai sau gio bat dau`); continue; }
    if (end - start < 120) { results.push(`❌ ${raw}: phien phai it nhat 2 phut`); continue; }
    const overlap = reserved.find((x) => start < x.end && x.start < end);
    if (overlap) { results.push(`❌ ${raw}: trung lich ${overlap.id.slice(0, 8)}`); continue; }

    try {
      const job = await callApi("/api/schedules", "POST", {
        account_number: ACCOUNT_NUMBER,
        start: `${date.iso}T${st}:00+07:00`,
        end: `${date.iso}T${en}:00+07:00`,
        bundle_index: bundle,
      });
      reserved.push({ start, end, id: String(job.id || "") });
      okCount += 1;
      results.push(`✅ ${date.d}/${date.m}/${date.y} ${st}-${en} · bo ${bundle} · ${String(job.id || "").slice(0, 8)} · ${job.state || "pending"}`);
    } catch (e) {
      results.push(`❌ ${date.d}/${date.m}/${date.y} ${st}-${en} · bo ${bundle}: ${e?.message || String(e)}`);
    }
  }

  return { text: `NBL ${ACCOUNT_NAME} · tao thanh cong ${okCount}/${parsed.items.length} lich\n` + results.join("\n") };
}

async function cancelHandler(ctx) {
  const id = String(ctx.args || "").trim();
  if (!id) return { text: "Dung: /huylich JOB_ID" };
  try {
    const job = await callApi(`/api/schedules/${encodeURIComponent(id)}/cancel`, "POST", {});
    return { text: `✅ ${String(job.id || id).slice(0, 8)} · ${job.state}` };
  } catch (e) { return { text: `❌ ${e?.message || String(e)}` }; }
}

async function stopHandler(ctx) {
  const id = String(ctx.args || "").trim();
  if (!id) return { text: "Dung: /dunglive JOB_ID" };
  try {
    const job = await callApi(`/api/schedules/${encodeURIComponent(id)}/stop`, "POST", {});
    return { text: `✅ ${String(job.id || id).slice(0, 8)} · ${job.state}` };
  } catch (e) { return { text: `❌ ${e?.message || String(e)}` }; }
}

function addCommand(api, name, description, handler, acceptsArgs = false) {
  api.registerCommand({ name, description, requireAuth: true, acceptsArgs, handler });
}

export default function register(api) {
  // Lenh Viet khong dau.
  addCommand(api, "huongdan", "Huong dan NBL Direct", async () => ({ text: helpText() }));
  addCommand(api, "trangthai", "Xem trang thai NBL LIVE", statusHandler);
  addCommand(api, "lich", "Xem lich NBL LIVE", schedulesHandler);
  addCommand(api, "taolich", "Tao mot hoac nhieu lich LIVE", createHandler, true);
  addCommand(api, "huylich", "Huy lich NBL chua chay", cancelHandler, true);
  addCommand(api, "dunglive", "Dung lich NBL dang chay", stopHandler, true);

  // Giu lenh cu de khong lam gay workflow dang dung.
  addCommand(api, "nbl_help", "Huong dan NBL Direct", async () => ({ text: helpText() }));
  addCommand(api, "nbl_status", "Trang thai NBL LIVE", statusHandler);
  addCommand(api, "nbl_schedules", "Liet ke lich NBL LIVE", schedulesHandler);
  addCommand(api, "nbl_create", "Tao lich LIVE NBL truc tiep", createHandler, true);
  addCommand(api, "nbl_cancel", "Huy lich NBL chua chay", cancelHandler, true);
  addCommand(api, "nbl_stop", "Dung lich NBL dang chay", stopHandler, true);
}
