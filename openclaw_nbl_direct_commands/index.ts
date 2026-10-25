import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

const ACCOUNT_NUMBER = 2;
const ACCOUNT_NAME = "giakhanhdoxe";
const TOKEN_FILE = process.env.NBL_API_TOKEN_FILE || "/mnt/c/Users/ADMIN/AppData/Local/NBL_LIVE_2/local_api_token.txt";
const TERMINAL = new Set(["finished", "cancelled", "skipped", "failed", "manual_stop"]);

function windowsHost(): string {
  if (process.env.NBL_API_HOST?.trim()) return process.env.NBL_API_HOST.trim();
  try {
    const text = execFileSync("ip", ["route", "show", "default"], { encoding: "utf8", timeout: 3000 });
    const parts = text.trim().split(/\s+/);
    const i = parts.indexOf("via");
    if (i >= 0 && parts[i + 1]) return parts[i + 1];
  } catch {}
  return "127.0.0.1";
}

function apiBase(): string {
  return (process.env.NBL_API_URL || `http://${windowsHost()}:${process.env.NBL_API_PORT || "8766"}`).replace(/\/$/, "");
}

function token(): string {
  const direct = process.env.NBL_API_TOKEN?.trim();
  if (direct) return direct;
  return readFileSync(TOKEN_FILE, "ascii").trim();
}

async function api(path: string, method = "GET", body?: unknown): Promise<any> {
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
  let value: any;
  try { value = await response.json(); }
  catch { value = { ok: false, error: `HTTP ${response.status}` }; }
  if (!response.ok || !value?.ok) throw new Error(String(value?.error || `HTTP ${response.status}`));
  return value.data;
}

function parseDate(raw: string): { y: number; m: number; d: number; iso: string } | null {
  const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(raw.trim());
  if (!match) return null;
  const d = Number(match[1]), m = Number(match[2]), y = Number(match[3]);
  if (d < 1 || d > 31 || m < 1 || m > 12 || y < 2020 || y > 2100) return null;
  return { y, m, d, iso: `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}` };
}

function parseTime(raw: string): { h: number; min: number; text: string } | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(raw.trim());
  if (!match) return null;
  const h = Number(match[1]), min = Number(match[2]);
  if (h < 0 || h > 23 || min < 0 || min > 59) return null;
  return { h, min, text: `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}` };
}

function epoch(dateIso: string, timeText: string): number {
  return Date.parse(`${dateIso}T${timeText}:00+07:00`) / 1000;
}

function fmt(ts: number): string {
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(ts * 1000));
}

function helpText(): string {
  return [
    "NBL Direct — không dùng AI/quota:",
    "/nbl_status — trạng thái nick + LIVE",
    "/nbl_schedules — lịch hiện tại",
    "/nbl_create DD/MM/YYYY HH:MM-HH:MM BO;HH:MM-HH:MM BO",
    "Ví dụ: /nbl_create 25/10/2026 17:45-18:45 1;19:45-20:45 1",
    "/nbl_cancel JOB_ID — hủy lịch chưa chạy",
    "/nbl_stop JOB_ID — dừng lịch đang chạy",
  ].join("\n");
}

export default function (apiPlugin: any) {
  apiPlugin.registerCommand({
    name: "nbl_help",
    description: "Hướng dẫn lệnh NBL trực tiếp, không dùng AI.",
    requireAuth: true,
    handler: async () => ({ text: helpText() }),
  });

  apiPlugin.registerCommand({
    name: "nbl_status",
    description: "Đọc trạng thái NBL LIVE trực tiếp, không dùng AI.",
    requireAuth: true,
    handler: async () => {
      try {
        const [accounts, live] = await Promise.all([api("/api/accounts"), api("/api/live/status")]);
        const a = (accounts || []).find((x: any) => Number(x.account_number ?? x.number) === ACCOUNT_NUMBER || x.account === ACCOUNT_NAME);
        if (!a) return { text: `Không tìm thấy nick ${ACCOUNT_NAME}.` };
        return { text: [
          `✅ ${ACCOUNT_NAME} · nick số ${ACCOUNT_NUMBER}`,
          `Studio: ${a.studio_connected ? "đã kết nối" : "chưa kết nối"}`,
          `Playlist: ${a.playlist_count ?? 0}`,
          `LIVE đang hoạt động: ${live?.count ?? 0}`,
        ].join("\n") };
      } catch (e: any) { return { text: `❌ NBL API: ${e?.message || String(e)}` }; }
    },
  });

  apiPlugin.registerCommand({
    name: "nbl_schedules",
    description: "Liệt kê lịch NBL LIVE trực tiếp, không dùng AI.",
    requireAuth: true,
    handler: async () => {
      try {
        const rows = (await api("/api/schedules")) || [];
        const mine = rows.filter((x: any) => Number(x.account_number) === ACCOUNT_NUMBER);
        if (!mine.length) return { text: `Nick ${ACCOUNT_NAME}: chưa có lịch.` };
        const active = mine.filter((x: any) => !TERMINAL.has(String(x.state)));
        const show = (active.length ? active : mine.slice(-10)).slice(0, 20);
        return { text: `${ACCOUNT_NAME} · ${mine.length} lịch (${active.length} chưa kết thúc)\n` + show.map((x: any) =>
          `${fmt(Number(x.start))} → ${new Intl.DateTimeFormat("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(Number(x.end) * 1000))} · bộ ${x.bundle_index ?? 0} · ${x.state} · ${String(x.id).slice(0, 8)}`
        ).join("\n") };
      } catch (e: any) { return { text: `❌ NBL API: ${e?.message || String(e)}` }; }
    },
  });

  apiPlugin.registerCommand({
    name: "nbl_create",
    description: "Tạo lịch LIVE NBL trực tiếp, không dùng AI.",
    acceptsArgs: true,
    requireAuth: true,
    handler: async (ctx: any) => {
      const raw = String(ctx.args || "").trim();
      const firstSpace = raw.indexOf(" ");
      if (firstSpace < 0) return { text: helpText() };
      const date = parseDate(raw.slice(0, firstSpace));
      if (!date) return { text: "Sai ngày. Dùng DD/MM/YYYY.\n" + helpText() };
      const specs = raw.slice(firstSpace + 1).split(";").map((s) => s.trim()).filter(Boolean);
      if (!specs.length) return { text: helpText() };

      let existing: any[];
      try { existing = (await api("/api/schedules")) || []; }
      catch (e: any) { return { text: `❌ Không đọc được lịch trước khi tạo: ${e?.message || String(e)}` }; }

      const results: string[] = [];
      const reserved = existing.filter((x: any) => Number(x.account_number) === ACCOUNT_NUMBER && !TERMINAL.has(String(x.state)))
        .map((x: any) => ({ start: Number(x.start), end: Number(x.end), id: String(x.id || "") }));

      for (const spec of specs) {
        const m = /^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})(?:\s+(\d{1,3}))?$/.exec(spec);
        if (!m) { results.push(`❌ ${spec}: cú pháp sai`); continue; }
        const st = parseTime(m[1]), en = parseTime(m[2]);
        const bundle = m[3] === undefined ? 1 : Number(m[3]);
        if (!st || !en || !Number.isInteger(bundle) || bundle < 0 || bundle > 200) { results.push(`❌ ${spec}: giờ/bộ không hợp lệ`); continue; }
        const start = epoch(date.iso, st.text), end = epoch(date.iso, en.text);
        if (!(end > start)) { results.push(`❌ ${spec}: giờ kết thúc phải sau giờ bắt đầu`); continue; }
        if (end - start < 120) { results.push(`❌ ${spec}: phiên phải ít nhất 2 phút`); continue; }
        const overlap = reserved.find((x) => start < x.end && x.start < end);
        if (overlap) { results.push(`❌ ${spec}: trùng lịch ${overlap.id.slice(0, 8)}`); continue; }
        try {
          const job = await api("/api/schedules", "POST", {
            account_number: ACCOUNT_NUMBER,
            start: `${date.iso}T${st.text}:00+07:00`,
            end: `${date.iso}T${en.text}:00+07:00`,
            bundle_index: bundle,
          });
          reserved.push({ start, end, id: String(job.id || "") });
          results.push(`✅ ${st.text}-${en.text} · bộ ${bundle} · ${String(job.id || "").slice(0, 8)} · ${job.state || "pending"}`);
        } catch (e: any) {
          results.push(`❌ ${st.text}-${en.text} · bộ ${bundle}: ${e?.message || String(e)}`);
        }
      }
      return { text: `NBL ${ACCOUNT_NAME} · ${date.d}/${date.m}/${date.y}\n` + results.join("\n") };
    },
  });

  apiPlugin.registerCommand({
    name: "nbl_cancel",
    description: "Hủy lịch NBL chưa chạy trực tiếp, không dùng AI.",
    acceptsArgs: true,
    requireAuth: true,
    handler: async (ctx: any) => {
      const id = String(ctx.args || "").trim();
      if (!id) return { text: "Dùng: /nbl_cancel JOB_ID" };
      try {
        const job = await api(`/api/schedules/${encodeURIComponent(id)}/cancel`, "POST", {});
        return { text: `✅ ${String(job.id || id).slice(0, 8)} · ${job.state}` };
      } catch (e: any) { return { text: `❌ ${e?.message || String(e)}` }; }
    },
  });

  apiPlugin.registerCommand({
    name: "nbl_stop",
    description: "Dừng lịch NBL đang chạy trực tiếp, không dùng AI.",
    acceptsArgs: true,
    requireAuth: true,
    handler: async (ctx: any) => {
      const id = String(ctx.args || "").trim();
      if (!id) return { text: "Dùng: /nbl_stop JOB_ID" };
      try {
        const job = await api(`/api/schedules/${encodeURIComponent(id)}/stop`, "POST", {});
        return { text: `✅ ${String(job.id || id).slice(0, 8)} · ${job.state}` };
      } catch (e: any) { return { text: `❌ ${e?.message || String(e)}` }; }
    },
  });
}
