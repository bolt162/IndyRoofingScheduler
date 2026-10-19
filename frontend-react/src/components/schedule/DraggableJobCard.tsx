import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { MapPin, X } from 'lucide-react';
import { ReadyCheckBadge } from '@/components/jobs/ReadyCheckBadge';
import { NoBuildDatesBadge } from '@/components/jobs/NoBuildDatesBadge';
import { cn } from '@/lib/utils';
import type { Job } from '@/types';

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
        className="touch-none select-none cursor-grab active:cursor-grabbing rounded-md border border-dashed border-primary/45 bg-card px-2.5 py-2 hover:border-primary/70"
        title="Planned here, not sent to JobNimbus yet. Drag to another day, or back to the list to remove."
      >
        <div className="flex items-center justify-between gap-2 pr-2">
          <span className="truncate text-xs font-semibold">{job.customer_name}</span>
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
    </div>
  );
}
