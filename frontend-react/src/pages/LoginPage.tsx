import { useAuth, SignIn } from '@clerk/clerk-react';
import { Navigate, useLocation } from 'react-router-dom';

/**
 * Login page — Clerk's hosted sign-in component.
 *
 * Clerk's <SignIn /> renders the full sign-in UI (email + Google OAuth, etc.,
 * depending on what's enabled in the Clerk dashboard). Anyone can sign up,
 * but they won't get past the ProtectedRoute approval check until an admin
 * flips `public_metadata.approved = true` in the Clerk dashboard.
 *
 * If the user is already signed in, we redirect to wherever they were trying
 * to go (or /). The approval gate then runs inside ProtectedRoute.
 */
export function LoginPage() {
  const { isLoaded, isSignedIn } = useAuth();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from || '/';

  if (!isLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/30">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (isSignedIn) {
    return <Navigate to={from} replace />;
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-muted/30 p-4 gap-6">
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Indy Roof Scheduler</h1>
        <p className="text-sm text-muted-foreground">Sign in to continue</p>
      </div>
      {/* Clerk renders its own card/styling — we just place it. */}
      <SignIn
        routing="hash"
        signUpUrl="/login#/sign-up"
        afterSignInUrl={from}
        afterSignUpUrl={from}
      />
      <p className="text-[11px] text-center text-muted-foreground max-w-md">
        New accounts require approval before access. After signing up, ask an
        administrator to approve your account.
      </p>
    </div>
  );
}
