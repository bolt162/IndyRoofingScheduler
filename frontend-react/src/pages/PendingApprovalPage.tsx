import { useUser, useClerk, useAuth } from '@clerk/clerk-react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useMe } from '@/api/auth';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Clock, LogOut, RefreshCw } from 'lucide-react';

/**
 * Pending Approval screen.
 *
 * Shown when the user is signed in via Clerk but their JWT's `approved` claim
 * is false. The user can sign out, or hit "Check again" to refetch /api/auth/me
 * in case an admin just approved them (and reload the Clerk session so a new
 * JWT with the updated metadata is minted).
 */
export function PendingApprovalPage() {
  const { isLoaded, isSignedIn } = useAuth();
  const { user } = useUser();
  const { signOut, session } = useClerk();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const meQuery = useMe();

  // Inline auth gate: this page is reachable directly via URL, so we have to
  // protect it ourselves (it's intentionally outside <ProtectedRoute />).
  if (!isLoaded) return null;
  if (!isSignedIn) return <Navigate to="/login" replace />;
  // If the user actually IS approved, bounce them home (e.g., they bookmarked
  // /pending from when they were pending, or an admin just approved them).
  if (meQuery.data?.approved) return <Navigate to="/" replace />;

  const handleCheckAgain = async () => {
    // Force Clerk to mint a fresh session token so the new public_metadata
    // (set in the dashboard) gets baked into the JWT we send to the backend.
    try {
      await session?.reload();
    } catch {
      // best-effort
    }
    await qc.invalidateQueries({ queryKey: ['auth-me'] });
  };

  const handleSignOut = async () => {
    await signOut();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md">
        <CardContent className="p-8 space-y-6 text-center">
          <div className="mx-auto h-12 w-12 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center">
            <Clock className="h-6 w-6" />
          </div>

          <div className="space-y-1.5">
            <h1 className="text-xl font-bold tracking-tight">Pending approval</h1>
            <p className="text-sm text-muted-foreground">
              Your account is waiting for administrator approval.
            </p>
            {user?.primaryEmailAddress?.emailAddress && (
              <p className="text-xs text-muted-foreground pt-2">
                Signed in as{' '}
                <span className="font-medium text-foreground">
                  {user.primaryEmailAddress.emailAddress}
                </span>
              </p>
            )}
          </div>

          <div className="rounded-md bg-muted/50 p-3 text-left text-xs text-muted-foreground space-y-1">
            <p className="font-medium text-foreground">What happens next?</p>
            <p>
              Contact your administrator and ask them to approve your account.
              Once approved, click <span className="font-medium">Check again</span>{' '}
              below to access the app.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Button onClick={handleCheckAgain} className="w-full">
              <RefreshCw className="h-4 w-4 mr-2" />
              Check again
            </Button>
            <Button variant="ghost" onClick={handleSignOut} className="w-full">
              <LogOut className="h-4 w-4 mr-2" />
              Sign out
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
