import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Map,
  CalendarDays,
  XCircle,
  Settings,
  Mail,
  ScrollText,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useBucketCounts } from '@/api/jobs';
import { useMe } from '@/api/auth';
import { useUIStore } from '@/stores/ui-store';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import logoWhite from '@/assets/irr-logo-white.png';
import markWhite from '@/assets/irr-mark-white.png';

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/map', label: 'Map View', icon: Map },
  { to: '/plan', label: 'Weekly Plan', icon: CalendarDays },
  { to: '/not-built', label: 'Not Built', icon: XCircle },
  { to: '/emails', label: 'Customer Emails', icon: Mail },
  { to: '/settings', label: 'Settings', icon: Settings },
];

interface SidebarProps {
  /** When rendered inside the mobile Sheet overlay — force-expanded view */
  mobileCompact?: boolean;
  /** Callback fired when a nav link is clicked — used to close the mobile sheet */
  onNavigate?: () => void;
}

export function Sidebar({ mobileCompact = false, onNavigate }: SidebarProps) {
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const { data: counts } = useBucketCounts();
  const { data: me } = useMe();
  // The activity log link only shows for the owner and admins (the API enforces it too)
  const items = me?.owner_or_admin
    ? [...navItems.slice(0, -1), { to: '/activity', label: 'Activity Log', icon: ScrollText }, navItems[navItems.length - 1]]
    : navItems;

  // On mobile inside the Sheet we always render expanded (regardless of store state)
  const expanded = mobileCompact ? true : sidebarOpen;

  return (
    <aside
      className={cn(
        'relative flex flex-col border-r bg-sidebar text-sidebar-foreground transition-all duration-200 h-full',
        mobileCompact
          ? 'w-full'
          : expanded
            ? 'w-64'
            : 'w-16',
      )}
    >
      {/* Header */}
      <div className={cn('flex h-20 items-center gap-2 border-b border-sidebar-border shrink-0', expanded ? 'px-4' : 'px-2 flex-col justify-center gap-1')}>
        {expanded ? (
          <div className="min-w-0">
            <img src={logoWhite} alt="Indy Roof & Restoration" className="h-10 w-auto" />
            <p className="mt-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-sidebar-primary">Scheduler</p>
          </div>
        ) : (
          <img src={markWhite} alt="Indy Roof" className="h-8 w-auto" />
        )}
        {/* Collapse toggle — only shown on desktop (not inside mobile Sheet) */}
        {!mobileCompact && (
          <Button
            variant="ghost"
            size="icon"
            className={cn('h-7 w-7 text-sidebar-foreground hover:bg-sidebar-accent hover:text-white', expanded && 'ml-auto')}
            onClick={toggleSidebar}
          >
            {expanded ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>
        )}
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 py-2">
        <nav className="flex flex-col gap-1 px-2">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => onNavigate?.()}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                  isActive
                    ? 'bg-sidebar-accent text-white shadow-[inset_3px_0_0_var(--sidebar-primary)]'
                    : 'text-sidebar-foreground/80',
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {expanded && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Bucket counts */}
        {expanded && counts && (
          <>
            <Separator className="my-3 bg-sidebar-border" />
            <div className="px-4 pb-2">
              <p className="mb-2 text-xs font-semibold uppercase text-sidebar-foreground/70">
                Job Buckets
              </p>
              <div className="space-y-1">
                {[
                  { key: 'to_schedule', label: 'To Schedule', color: 'bg-blue-500' },
                  { key: 'scheduled', label: 'Scheduled', color: 'bg-green-500' },
                  { key: 'other_trades', label: 'Other Trades', color: 'bg-purple-500' },
                  { key: 'primary_completed', label: 'Primary Completed', color: 'bg-orange-500' },
                ].map(({ key, label, color }) => (
                  <div key={key} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className={cn('h-2 w-2 rounded-full', color)} />
                      <span className="text-sidebar-foreground/85">{label}</span>
                    </div>
                    <Badge className="h-5 px-1.5 text-[10px] bg-sidebar-accent text-white">
                      {counts[key] ?? 0}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </ScrollArea>
    </aside>
  );
}
