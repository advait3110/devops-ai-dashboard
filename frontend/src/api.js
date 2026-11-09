/*
 * One small wrapper around fetch() for every backend call.
 * - Relative URLs ("/api/...") work in dev (Vite proxy) and production (Nginx).
 * - Errors become ApiError objects carrying the backend's "detail" and "hint",
 *   so pages can show "Jenkins is not configured - set JENKINS_URL ..." instead
 *   of a generic failure.
 * No axios needed: fetch is built into every browser.
 */

const BASE = import.meta.env.VITE_API_URL || "";

export class ApiError extends Error {
  constructor(message, status, hint = "") {
    super(message);
    this.status = status;
    this.hint = hint;
  }
}

async function request(method, path, body, timeoutMs = 90000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    const msg = err.name === "AbortError" ? "The request timed out" : "Cannot reach the backend";
    throw new ApiError(msg, 0, "Start it with: cd backend && uvicorn app.main:app --reload --port 8000");
  } finally {
    clearTimeout(timer);
  }

  let data;
  const text = await response.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}`;
    throw new ApiError(detail, response.status, data?.hint || "");
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  del: (path) => request("DELETE", path),
};

export const qs = (params) =>
  new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""),
  ).toString();
