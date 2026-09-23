/** Resolve a same-origin proxy path, full WebSocket URL, or entered host. */
export function buildDirectWsUrl(raw, pageUrl = globalThis.location?.href) {
  let s = (raw || "").trim();
  if (!s) return "";
  if (s.startsWith("/") && !s.startsWith("//")) {
    const u = new URL(s, pageUrl);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    return u.toString();
  }
  if (!/^wss?:\/\//i.test(s)) {
    if (/^https?:\/\//i.test(s)) s = s.replace(/^http/i, "ws");
    else s = (/^(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(s) ? "ws://" : "wss://") + s;
  }
  const u = new URL(s);
  if (!["ws:", "wss:"].includes(u.protocol)) throw new Error("Use a WebSocket server URL");
  if (u.pathname === "/") u.pathname = "/v1/realtime";
  return u.toString();
}
