const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export function getApiBase() {
  return API_BASE;
}

export async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST ${path} failed: ${res.status} ${text}`);
  }
  return res.json();
}

export function getOrCreateDeviceId() {
  if (typeof window === "undefined") return "";
  const key = "fridge-device-id";
  const found = localStorage.getItem(key);
  if (found) return found;

  const generated = `device-${crypto.randomUUID()}`;
  localStorage.setItem(key, generated);
  return generated;
}

export function statusLabelToClass(status) {
  if (status === "기한 지남") return "chip chip-risk";
  if (status === "임박") return "chip chip-imminent";
  if (status === "폐기") return "chip chip-discarded";
  if (status === "소진") return "chip chip-consumed";
  return "chip chip-owned";
}
