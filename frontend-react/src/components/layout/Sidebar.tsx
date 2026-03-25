import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Map,
  CalendarDays,
  XCircle,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useBucketCounts } from '@/api/jobs';
import { useUIStore } from '@/stores/ui-store';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/map', label: 'Map View', icon: Map },
  { to: '/plan', label: 'Weekly Plan', icon: CalendarDays },
  { to: '/not-built', label: 'Not Built', icon: XCircle },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const { data: counts } = useBucketCounts();

  return (
    <aside
      className={cn(
        'relative flex flex-col border-r bg-sidebar text-sidebar-foreground transition-all duration-200',
        sidebarOpen ? 'w-64' : 'w-16'
      )}
    >
      {/* Header */}
      <div className="flex h-14 items-center gap-2 border-b px-4">
        {sidebarOpen && (
          <h2 className="text-sm font-semibold tracking-tight truncate">
            Indy Roof Scheduler
          </h2>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto h-7 w-7"
          onClick={toggleSidebar}
        >
          {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </Button>
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 py-2">
        <nav className="flex flex-col gap-1 px-2">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-primary'
                    : 'text-sidebar-foreground/70'
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {sidebarOpen && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Bucket counts */}
        {sidebarOpen && counts && (
          <>
            <Separator className="my-3" />
            <div className="px-4 pb-2">
              <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                Job Buckets
              </p>
              <div className="space-y-1">
                {[
                  { key: 'to_schedule', label: 'To Schedule', color: 'bg-blue-500' },
                  { key: 'scheduled', label: 'Scheduled', color: 'bg-green-500' },
                  { key: 'primary_complete', label: 'Primary Complete', color: 'bg-purple-500' },
                  { key: 'waiting_on_trades', label: 'Waiting on Trades', color: 'bg-yellow-500' },
                  { key: 'review_for_completion', label: 'Review', color: 'bg-orange-500' },
                ].map(({ key, label, color }) => (
                  <div key={key} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className={cn('h-2 w-2 rounded-full', color)} />
                      <span className="text-muted-foreground">{label}</span>
                    </div>
                    <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
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
