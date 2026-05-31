import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { X } from 'lucide-react';
import { JobCard } from '@/components/jobs/JobCard';
import { cn } from '@/lib/utils';
import type { Job } from '@/types';

/**
 * Draggable job card for the Weekly Plan day grid.
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
      <div {...listeners} {...attributes} className="touch-none">
        <JobCard job={job} compact />
      </div>
    </div>
  );
}
