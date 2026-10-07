import type { UserRole } from "./types";

// ============================================================================
// Token Storage — localStorage-based JWT management
//
// Security notes:
// - Only opaque JWT strings stored here. Never PII or financial data.
// - Axios interceptor clears all tokens on 401 response.
// - Flask validates JWT server-side on every request.
// ============================================================================

const TOKEN_KEY   = "ofds_access_token";
const REFRESH_KEY = "ofds_refresh_token";
const ROLE_KEY    = "ofds_user_role";
const NAME_KEY    = "ofds_user_name";

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function getUserRole(): UserRole | null {
  const role = localStorage.getItem(ROLE_KEY);
  if (role === "user" || role === "admin" || role === "super_admin") {
    return role;
  }
  return null;
}

export function getUserName(): string | null {
  return localStorage.getItem(NAME_KEY);
}

export function setTokens(
  accessToken: string,
  refreshToken: string,
  userRole: string,
  userName?: string
): void {
  localStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_KEY, refreshToken);
  localStorage.setItem(ROLE_KEY, userRole);
  if (userName) {
    localStorage.setItem(NAME_KEY, userName);
  }
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(ROLE_KEY);
  localStorage.removeItem(NAME_KEY);
}

export function isAuthenticated(): boolean {
  return !!getAccessToken();
}
