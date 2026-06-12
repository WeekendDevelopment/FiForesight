/*
 * Alerts & Notifications client (Feature 9 — "Alerts" tab).
 *
 * Routes through the Next.js /api/alerts proxies → FastAPI backend (never hits
 * Supabase directly). Every call forwards the Supabase access token as a Bearer
 * header; without it the backend returns 401. The backend re-validates input and
 * reads/writes the alert tables with the caller's forwarded JWT, so Supabase RLS
 * enforces per-user ownership.
 *
 * Web-Push helpers register the service worker, subscribe with the server VAPID
 * public key, and POST the subscription to the backend.
 */
import type { AlertRule, AlertRuleType, AlertOperator, AlertFire } from '../types';

function authHeaders(token: string): HeadersInit {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

async function parseOrThrow(res: Response): Promise<unknown> {
  let body: unknown = null;
  try { body = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = (body as { detail?: string } | null)?.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return body;
}

export interface NewRule {
  symbol:    string;
  type:      AlertRuleType;
  operator?: AlertOperator | null;
  threshold?: number | null;
}

// ── Rules CRUD ───────────────────────────────────────────────────────────────

export async function fetchRules(token: string): Promise<AlertRule[]> {
  const res = await fetch('/api/alerts/rules', { headers: authHeaders(token) });
  const body = await parseOrThrow(res) as { rules?: AlertRule[] };
  return body.rules ?? [];
}

export async function createRule(token: string, rule: NewRule): Promise<AlertRule> {
  const res = await fetch('/api/alerts/rules', {
    method:  'POST',
    headers: authHeaders(token),
    body:    JSON.stringify({
      symbol:    rule.symbol.toUpperCase(),
      type:      rule.type,
      operator:  rule.operator ?? null,
      threshold: rule.threshold ?? null,
    }),
  });
  const body = await parseOrThrow(res) as { rule?: AlertRule };
  if (!body.rule) throw new Error('Malformed response: missing rule.');
  return body.rule;
}

export async function setRuleActive(token: string, id: string, active: boolean): Promise<AlertRule> {
  const res = await fetch(`/api/alerts/rules/${encodeURIComponent(id)}`, {
    method:  'PATCH',
    headers: authHeaders(token),
    body:    JSON.stringify({ active }),
  });
  const body = await parseOrThrow(res) as { rule?: AlertRule };
  if (!body.rule) throw new Error('Malformed response: missing rule.');
  return body.rule;
}

export async function deleteRule(token: string, id: string): Promise<void> {
  const res = await fetch(`/api/alerts/rules/${encodeURIComponent(id)}`, {
    method:  'DELETE',
    headers: authHeaders(token),
  });
  await parseOrThrow(res);
}

export async function fetchFires(token: string): Promise<AlertFire[]> {
  const res = await fetch('/api/alerts/fires', { headers: authHeaders(token) });
  const body = await parseOrThrow(res) as { fires?: AlertFire[] };
  return body.fires ?? [];
}

// ── Web Push ─────────────────────────────────────────────────────────────────

/** True when the browser supports the Push API + service workers. */
export function pushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

async function getVapidPublicKey(token: string): Promise<{ public_key: string; configured: boolean }> {
  const res = await fetch('/api/alerts/vapid-public-key', { headers: authHeaders(token) });
  return await parseOrThrow(res) as { public_key: string; configured: boolean };
}

/** Base64url → Uint8Array, as required by PushManager.subscribe. Backed by an
 *  explicit ArrayBuffer so the result satisfies BufferSource under strict DOM
 *  lib typings (a plain `new Uint8Array(n)` infers ArrayBufferLike). */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const arr = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

/**
 * Request notification permission, register the service worker, subscribe to
 * push with the server VAPID key, and persist the subscription on the backend.
 * Throws a human-readable Error on any failure.
 */
export async function enablePushNotifications(token: string): Promise<void> {
  if (!pushSupported()) throw new Error('This browser does not support push notifications.');

  const { public_key, configured } = await getVapidPublicKey(token);
  if (!configured || !public_key) {
    throw new Error('Push notifications are not configured on the server yet.');
  }

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    throw new Error('Notification permission was denied.');
  }

  const reg = await navigator.serviceWorker.register('/sw.js');
  await navigator.serviceWorker.ready;

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    });
  }

  const json = sub.toJSON();
  const res = await fetch('/api/alerts/subscribe', {
    method:  'POST',
    headers: authHeaders(token),
    body:    JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
  });
  await parseOrThrow(res);
}

/** True when this browser already has an active push subscription. */
export async function isPushSubscribed(): Promise<boolean> {
  if (!pushSupported()) return false;
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    if (!reg) return false;
    const sub = await reg.pushManager.getSubscription();
    return !!sub;
  } catch {
    return false;
  }
}
