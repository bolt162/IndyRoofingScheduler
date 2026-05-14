import { LogOut, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useUser, useClerk } from '@clerk/clerk-react';
import { toast } from 'sonner';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

/**
 * Top-bar user menu. Shows the signed-in user's avatar (Clerk profile image
 * if available) and a dropdown with sign-out.
 *
 * Pulls identity directly from Clerk via `useUser()` — no local store needed.
 *
 * Note on markup: we intentionally do NOT use <DropdownMenuLabel> for the
 * header row. DropdownMenuLabel wraps Base UI's <MenuGroupLabel> which
 * requires a surrounding <Menu.Group> — using it bare crashes the dropdown
 * at open time. A plain styled <div> is simpler and avoids the trap.
 */
export function UserMenu() {
  const { user, isLoaded } = useUser();
  const { signOut } = useClerk();
  const navigate = useNavigate();

  if (!isLoaded || !user) return null;

  const email = user.primaryEmailAddress?.emailAddress ?? '';
  const name =
    user.fullName ||
    [user.firstName, user.lastName].filter(Boolean).join(' ') ||
    '';
  const pictureUrl = user.imageUrl;

  const initials = (name || email)
    .split(/[\s@]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('');

  const handleSignOut = async () => {
    await signOut();
    toast.success('Signed out');
    navigate('/login', { replace: true });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="inline-flex items-center gap-2 h-8 px-2 rounded-md hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 transition-colors"
        aria-label="Account menu"
      >
        {pictureUrl ? (
          <img
            src={pictureUrl}
            alt=""
            className="h-6 w-6 rounded-full object-cover"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="h-6 w-6 rounded-full bg-primary/10 text-primary text-[10px] font-semibold flex items-center justify-center">
            {initials || <User className="h-3 w-3" />}
          </div>
        )}
        <span className="hidden md:inline text-xs text-muted-foreground truncate max-w-[140px]">
          {name || email}
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[220px]">
        <div className="px-1.5 py-1.5">
          <div className="flex flex-col gap-0.5">
            <span className="font-medium text-sm leading-tight">
              {name || 'User'}
            </span>
            <span className="text-[11px] text-muted-foreground truncate">
              {email}
            </span>
          </div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={handleSignOut}
          className="text-destructive focus:text-destructive"
        >
          <LogOut className="h-4 w-4 mr-2" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
