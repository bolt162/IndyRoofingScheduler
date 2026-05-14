/**
 * Backend auth query — calls /api/auth/me to read the approval state from
 * the JWT custom claims that Clerk injected from public_metadata.
 *
 * Clerk owns sign-in / sign-up / sign-out — those live in the Clerk hooks
 * (`useAuth`, `useUser`, `<SignIn />`). This file only exposes the backend's
 * view of the user so the route guard can decide between app vs. pending.
 */
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@clerk/clerk-react';
import api from './client';

export interface BackendMe {
  id: string;
  email: string;
  name: string;
  approved: boolean;
  admin: boolean;
}

/**
 * Verify the current Clerk session against our backend and read approval state.
 * Only enabled once Clerk has loaded and the user is signed in.
 */
export function useMe() {
  const { isLoaded, isSignedIn } = useAuth();
  return useQuery<BackendMe>({
    queryKey: ['auth-me'],
    queryFn: async () => {
      const { data } = await api.get<BackendMe>('/auth/me');
      return data;
    },
    enabled: isLoaded && !!isSignedIn,
    retry: false,
    // Approval state changes rarely; refetch on focus is enough to pick up
    // a fresh approval without spamming the backend.
    staleTime: 5 * 60 * 1000,
  });
}
