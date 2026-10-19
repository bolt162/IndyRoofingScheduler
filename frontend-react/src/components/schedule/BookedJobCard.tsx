import { HardHat, Lock, MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Job } from '@/types';

/** "DCT Construction - Roof Crew" -> "DCT Construction" */
export function crewShort(name: string) {
  return name.split(' - ')[0].trim();
}

/** The work order JobNimbus has on this date (trade + number), if we know it. */
function bookedWorkOrder(job: Job) {
  return (job.jn_work_orders ?? []).find(
    (w) => w.status.toLowerCase() === 'pending start' && w.start === job.jn_start_date,
  );
}

/**
 * A build that's already booked in JobNimbus. Read-only on the Weekly Plan: JobNimbus is where
 * the date lives, so it can't be dragged here (that would only change the app, not the booking).
 */
export function BookedJobCard({ job }: { job: Job }) {
  const wo = bookedWorkOrder(job);
  const crews = (job.jn_crews ?? []).map(crewShort);

  return (
    <div
      className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2"
      title="Booked in JobNimbus. To change the date, change it on the work order in JobNimbus."
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-semibold">{job.customer_name}</span>
        <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-slate-200/80 px-1 py-px text-[9px] font-medium text-slate-700">
          <Lock className="h-2.5 w-2.5" />
          Booked
        </span>
      </div>
      <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-muted-foreground">
        <MapPin className="h-3 w-3 shrink-0" />
        {job.address}
      </p>
      <p
        className={cn(
          'mt-1 flex items-center gap-1 truncate text-[11px]',
          crews.length ? 'text-slate-800' : 'text-amber-700',
        )}
      >
        <HardHat className="h-3 w-3 shrink-0" />
        {crews.length ? crews.join(', ') : 'No crew on the work order'}
        {wo && <span className="text-muted-foreground">· {wo.trade || 'Work order'} {wo.number}</span>}
      </p>
    </div>
  );
}
