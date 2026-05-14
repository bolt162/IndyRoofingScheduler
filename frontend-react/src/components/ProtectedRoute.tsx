import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@clerk/clerk-react';
import { useMe } from '@/api/auth';

/**
 * Route guard for the app shell — three-state logic.
 *
 *   1. Not signed in (Clerk says no session)           → /login
 *   2. Signed in but `approved=false` (per backend /me) → /pending
 *   3. Signed in + approved=true                        → render <Outlet />
 *
 * This is the single security boundary on the frontend. Even though the
 * backend also enforces approval on every /api/* endpoint (via
 * get_approved_user), this guard prevents the app shell or any cached data
 * from rendering for unapproved users.
 *
 * NOTE: The `approved` flag comes from the Clerk-signed JWT claim, which is
 * derived from `public_metadata.approved` set by an admin in the Clerk
 * dashboard. The client cannot spoof it.
 *
 * /pending is rendered on its own (outside this guard) so unapproved users
 * have a destination — see App.tsx and PendingApprovalPage.
 */
export function ProtectedRoute() {
  const location = useLocation();
  const { isLoaded, isSignedIn } = useAuth();
  const meQuery = useMe();

  // Clerk still bootstrapping — show loading to avoid flashing /login.
  if (!isLoaded) {
    return <Splash />;
  }

  // No Clerk session at all → /login, remembering where they were headed.
  if (!isSignedIn) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  // Signed in but backend hasn't responded yet.
  if (meQuery.isLoading || !meQuery.data) {
    if (meQuery.isError) {
      return (
        <div className="min-h-screen flex flex-col items-center justify-center gap-2 p-4 text-center">
          <p className="text-sm text-destructive">Unable to verify your session.</p>
          <p className="text-xs text-muted-foreground">
            The server may be unreachable. Please refresh in a moment.
          </p>
        </div>
      );
    }
    return <Splash />;
  }

  // Backend says signed in but not approved → pending screen.
  if (!meQuery.data.approved) {
    return <Navigate to="/pending" replace />;
  }

  return <Outlet />;
}

function Splash() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-sm text-muted-foreground">Loading…</p>
    </div>
  );
}
