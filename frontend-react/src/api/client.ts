import axios from 'axios';

/**
 * Axios client that injects a Clerk-issued JWT on every request.
 *
 * Why a getter callback?
 *   Clerk's `getToken()` lives on the `useAuth()` hook, which can only be
 *   called inside React components. Axios interceptors run outside React, so
 *   we let a top-level component register the getter via `setClerkTokenGetter`
 *   and the interceptor reaches into that closure when it needs a fresh token.
 *
 *   The getter is wired by <ClerkTokenBridge> rendered inside <ClerkProvider>
 *   in main.tsx — see that file for the registration.
 */

type TokenGetter = () => Promise<string | null>;

let _tokenGetter: TokenGetter | null = null;

export function setClerkTokenGetter(fn: TokenGetter | null) {
  _tokenGetter = fn;
}

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// Attach a fresh Clerk JWT to every request. If Clerk hasn't loaded yet or the
// user is signed out, we let the request go through without an Authorization
// header — the backend will respond 401 and the route guard handles redirect.
api.interceptors.request.use(async (config) => {
  if (_tokenGetter) {
    try {
      const token = await _tokenGetter();
      if (token) {
        config.headers = config.headers ?? {};
        (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
      }
    } catch {
      // Token fetch failed (Clerk loading, network blip) — proceed unauthenticated.
    }
  }
  return config;
});

export default api;
