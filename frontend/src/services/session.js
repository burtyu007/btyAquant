import { ref } from "vue";

const TOKEN_KEY = "quant_platform_token";
const USER_KEY = "quant_platform_user";
const sessionUser = ref(readUser());

function readUser() {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  sessionUser.value = user;
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  sessionUser.value = null;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  return sessionUser.value;
}

export function useSessionUser() {
  return sessionUser;
}

export async function refreshSessionUser() {
  const token = getToken();
  if (!token) {
    clearSession();
    return null;
  }
  const baseUrl = import.meta.env.VITE_API_BASE_URL || "/api";
  const response = await fetch(`${baseUrl}/auth/me`, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });
  if (!response.ok) {
    clearSession();
    throw new Error("session_refresh_failed");
  }
  const user = await response.json();
  saveSession(token, user);
  return user;
}
