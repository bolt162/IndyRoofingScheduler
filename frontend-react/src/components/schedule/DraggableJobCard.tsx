import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { toast } from 'sonner';
import { AlertTriangle, CalendarDays, HardHat, MapPin, Send, X } from 'lucide-react';
import { ReadyCheckBadge } from '@/components/jobs/ReadyCheckBadge';
import { NoBuildDatesBadge } from '@/components/jobs/NoBuildDatesBadge';
import { useUpdateJob } from '@/api/jobs';
import { useCrews } from '@/api/settings';
import { CrewNotesButton } from './CrewNotesButton';
import { cn } from '@/lib/utils';
import { JobName } from '@/components/jobs/JobName';
import type { Crew, Job } from '@/types';

/** Active crews that do this job's trade (a roof repair is still roofing), best rank first. */
function crewsForJob(crews: Crew[] | undefined, job: Job) {
  const active = (crews ?? []).filter((c) => c.is_active);
  const booking = job.work_trade ?? job.primary_trade ?? '';  // gutters or siding after the main trade: that trade's crews
  const trade = booking.replace(/_repair$/, '');
  const fit = active.filter((c) => !trade || c.trades.includes(trade) || c.trades.includes(booking));
  return (fit.length ? fit : active).sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
}

/** Sent to JobNimbus for the day it's planned on; the next sync turns it into a Booked card. */
export function sentToJobNimbus(job: Job) {
  const s = job.jn_push_steps;
  return !!s && s.date === job.planned_date && !!s.tasks;
}

/** Build days: picked here, else the suggestion from the work order, else the job's duration. */
function DaysPicker({ job }: { job: Job }) {
  const updateJob = useUpdateJob();
  const sug = job.days_suggestion;
  const value = job.planned_days ?? sug?.days ?? job.duration_days ?? 1;
  const isSuggested = !job.planned_days && !!sug;
  const title = sug ? `Suggested ${sug.days} day${sug.days > 1 ? 's' : ''}: ${sug.why}` : 'Build days';

  return (
    <label
      className="mt-0.5 flex items-center gap-1 text-[11px] text-slate-800"
      title={title}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <CalendarDays className="h-3 w-3 shrink-0" />
      <span className="sr-only">Build days for {job.customer_name}</span>
      <select
        value={value}
        disabled={updateJob.isPending}
        onChange={async (e) => {
          const n = Number(e.target.value);
          try {
            // Picking the suggested number again goes back to following the suggestion
            await updateJob.mutateAsync({ id: job.id, update: { planned_days: sug && n === sug.days ? null : n } });
          } catch {
            toast.error("Couldn't save the days. Try again.");
          }
        }}
        className="cursor-pointer rounded border border-transparent bg-transparent py-px pr-1 hover:border-input focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-60"
      >
        {[1, 2, 3, 4, 5].map((n) => (
          <option key={n} value={n}>{n} day{n > 1 ? 's' : ''}</option>
        ))}
      </select>
      {isSuggested && <span className="truncate text-[10px] text-muted-foreground">suggested</span>}
    </label>
  );
}

/** Crew for the build. Sits outside the drag handle so picking one never starts a drag. */
function CrewPicker({ job }: { job: Job }) {
  const { data: crews } = useCrews();
  const updateJob = useUpdateJob();
  const options = crewsForJob(crews, job);
  const missing = !job.planned_crew_id;

  return (
    <label
      className={cn(
        'mt-1 flex items-center gap-1 text-[11px]',
        missing ? 'text-amber-700' : 'text-slate-800',
      )}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <HardHat className="h-3 w-3 shrink-0" />
      <span className="sr-only">Crew for {job.customer_name}</span>
      <select
        value={job.planned_crew_id ?? ''}
        disabled={updateJob.isPending}
        onChange={async (e) => {
          const id = e.target.value ? Number(e.target.value) : null;
          try {
            await updateJob.mutateAsync({ id: job.id, update: { planned_crew_id: id } });
          } catch {
            toast.error("Couldn't save the crew. Try again.");
          }
        }}
        className="min-w-0 flex-1 cursor-pointer truncate rounded border border-transparent bg-transparent py-px pr-1 hover:border-input focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-60"
      >
        <option value="">Pick a crew</option>
        {options.map((c) => (
          <option key={c.id} value={c.id}>{c.name}</option>
        ))}
      </select>
    </label>
  );
}

/**
 * A job planned on the Weekly Plan but not sent to JobNimbus yet. Dashed so it reads as a
 * pencilled-in plan next to the solid gray builds JobNimbus has booked.
 *
 * When `onUnschedule` is provided (scheduled cards in a day column), a small ✕
 * button is rendered in the corner so the job can be removed from the schedule
 * without dragging. The button sits outside the drag listeners and stops
 * propagation so a click never starts a drag.
 */
export function DraggableJobCard({
  job,
  onUnschedule,
}: {
  job: Job;
  onUnschedule?: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `job-${job.id}`,
    data: { job },
  });

  const style = transform
    ? { transform: CSS.Translate.toString(transform) }
    : undefined;

  return (
    <div ref={setNodeRef} style={style} className={cn('relative', isDragging && 'opacity-50 z-50')}>
      {onUnschedule && (
        <button
          type="button"
          aria-label={`Remove ${job.customer_name} from schedule`}
          title="Remove from schedule"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onUnschedule();
          }}
          className="absolute -top-1.5 -right-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full border bg-background text-muted-foreground shadow-sm hover:bg-red-50 hover:text-red-600 hover:border-red-300"
        >
          <X className="h-3 w-3" />
        </button>
      )}
      <div
        {...listeners}
        {...attributes}
        className="touch-none select-none cursor-grab active:cursor-grabbing rounded-t-md border border-b-0 border-dashed border-primary/45 bg-card px-2.5 py-2 hover:border-primary/70"
        title="Planned here, not sent to JobNimbus yet. Drag to another day, or back to the list to remove."
      >
        <div className="flex items-center justify-between gap-2 pr-2">
          <JobName job={job} className="text-xs font-semibold" />
          <span className="shrink-0 rounded bg-primary/10 px-1 py-px text-[9px] font-medium text-primary">Planned</span>
        </div>
        <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-muted-foreground">
          <MapPin className="h-3 w-3 shrink-0" />
          {job.address}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1 empty:hidden">
          <ReadyCheckBadge job={job} small />
          <NoBuildDatesBadge windows={job.no_build_dates} small />
        </div>
      </div>
      <div className="rounded-b-md border border-t-0 border-dashed border-primary/45 bg-card px-2.5 pb-1.5 pt-1">
        <CrewPicker job={job} />
        <DaysPicker job={job} />
        <CrewNotesButton job={job} />
        {sentToJobNimbus(job) ? (
          <p className="mt-0.5 flex items-center gap-1 text-[10px] text-emerald-700">
            <Send className="h-2.5 w-2.5 shrink-0" />
            Sent to JobNimbus · shows as Booked after the next sync
          </p>
        ) : job.jn_push_error ? (
          <p className="mt-0.5 flex items-start gap-1 text-[10px] leading-snug text-red-700">
            <AlertTriangle className="mt-px h-2.5 w-2.5 shrink-0" />
            {job.jn_push_error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
