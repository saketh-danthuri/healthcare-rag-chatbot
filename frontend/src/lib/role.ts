/* ============================================================
   Permission role + user identity helpers (localStorage-backed).

   Role governs whether the SERVER masks PHI in the assistant's output
   (clinician = unmasked, general = masked). It is sent on each request via
   the X-User-Role header; the server enforces it. This is demo-grade identity
   (no real login) — the server never trusts the client to do the masking.
   ============================================================ */

import type { UserRole } from "./types";

const ROLE_KEY = "user-role";
const USER_ID_KEY = "user-id";

const DEFAULT_ROLE: UserRole = "general"; // Most restrictive: masked.

export function getRole(): UserRole {
  if (typeof window === "undefined") return DEFAULT_ROLE;
  const raw = localStorage.getItem(ROLE_KEY);
  return raw === "clinician" || raw === "general" ? raw : DEFAULT_ROLE;
}

export function setRole(role: UserRole): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ROLE_KEY, role);
}

/** Stable per-browser user id, sent as X-User-Id (identifies the owner). */
export function getUserId(): string {
  if (typeof window === "undefined") return "anonymous";
  let id = localStorage.getItem(USER_ID_KEY);
  if (!id) {
    id = `user-${crypto.randomUUID()}`;
    localStorage.setItem(USER_ID_KEY, id);
  }
  return id;
}
