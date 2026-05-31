import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { differenceInDays, parseISO } from 'date-fns';
import { MapPin, Star, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { WeatherBadge } from '@/components/jobs/WeatherBadge';
import { cn } from '@/lib/utils';
import type { Job } from '@/types';

/**
 * Slim, draggable job row purpose-built for the Weekly Plan unassigned sidebar.
 *
 * The full (compact) JobCard packs a score badge plus Edit / Update-AI buttons and
 * several badge rows into the narrow sidebar, where it wraps and clips. This row
 * shows only what a scheduler needs to choose a job — name, address, score, and a
 * few key flags — and reads cleanly at the sidebar's width. It keeps the same
 * useDraggable contract (id `job-<id>`, data `{ job }`) so drag-to-day is unchanged.
 */
export function UnassignedJobRow({ job }: { job: Job }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `job-${job.id}`,
    data: { job },
  });

  const style = transform ? { transform: CSS.Translate.toString(transform) } : undefined;

  const daysInQueue = job.date_entered
    ? differenceInDays(new Date(), parseISO(job.date_entered))
    : null;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className={cn(
        'touch-none select-none rounded-md border bg-card px-2.5 py-2 cursor-grab active:cursor-grabbing',
        'hover:border-primary/50 hover:shadow-sm transition-colors',
        job.must_build && 'ring-1 ring-red-400/60 bg-red-50/40',
        isDragging && 'opacity-50 z-50',
      )}
    >
      {/* Line 1: name + score */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold truncate">{job.customer_name}</span>
        <Badge variant="outline" className="font-mono text-[10px] tabular-nums shrink-0 px-1 py-0">
          {job.score.toFixed(0)}
        </Badge>
      </div>

      {/* Line 2: address */}
      <p className="text-[11px] text-muted-foreground flex items-center gap-1 truncate mt-0.5">
        <MapPin className="h-3 w-3 shrink-0" />
        {job.address}
      </p>

      {/* Line 3: key flags */}
      <div className="flex flex-wrap items-center gap-1 mt-1">
        {job.primary_trade && (
          <Badge variant="secondary" className="text-[9px] px-1 py-0 capitalize">
            {job.primary_trade}
          </Badge>
        )}
        {job.must_build && (
          <Badge variant="outline" className="text-[9px] px-1 py-0 gap-0.5 bg-red-100 text-red-800 border-red-300">
            <Star className="h-2.5 w-2.5" />
            Must-Build
          </Badge>
        )}
        {daysInQueue !== null && (
          <Badge variant="outline" className="text-[9px] px-1 py-0 gap-0.5 text-muted-foreground">
            <Clock className="h-2.5 w-2.5" />
            {daysInQueue}d
          </Badge>
        )}
        <WeatherBadge
          status={job.weather_status}
          detail={job.weather_detail}
          jobId={job.id}
          customerName={job.customer_name}
        />
      </div>
    </div>
  );
}
