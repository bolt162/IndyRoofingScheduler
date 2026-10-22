import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { toast } from 'sonner';
import { CalendarDays, Check, HardHat, MapPin, Sparkles, X } from 'lucide-react';
import { useClearSuggestions, useKeepSuggestions } from '@/api/schedule';
import { useCrews, usePMs } from '@/api/settings';
import { ReadyCheckBadge } from '@/components/jobs/ReadyCheckBadge';
import { NoBuildDatesBadge } from '@/components/jobs/NoBuildDatesBadge';
import { cn } from '@/lib/utils';
import { JobName } from '@/components/jobs/JobName';
import type { Job } from '@/types';

/**
 * A build "Suggest builds" pencilled in. Not a plan and never sent to JobNimbus: Keep turns it
 * into a normal planned card, ✕ dismisses it, and dragging it to another day plans it there.
 */
export function SuggestedJobCard({ job }: { job: Job }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `job-${job.id}`,
    data: { job },
  });
  const { data: crews } = useCrews();
  const { data: pms } = usePMs();
  const keep = useKeepSuggestions();
  const clear = useClearSuggestions();
  const busy = keep.isPending || clear.isPending;
  const crew = crews?.find((c) => c.id === job.suggested_crew_id);
  const pm = pms?.find((p) => p.id === job.suggested_pm_id);
  const days = job.suggested_days ?? 1;
  const stop = (e: React.SyntheticEvent) => e.stopPropagation();

  const onKeep = async () => {
    try {
      await keep.mutateAsync({ job_ids: [job.id] });
      toast.success(`Kept ${job.customer_name}. It's planned now; push it when you're ready.`);
    } catch {
      toast.error("Couldn't keep it. Try again.");
    }
  };
  const onDismiss = async () => {
    try {
      await clear.mutateAsync({ job_ids: [job.id] });
    } catch {
      toast.error("Couldn't remove the suggestion. Try again.");
    }
  };

  return (
    <div
      ref={setNodeRef}
      style={transform ? { transform: CSS.Translate.toString(transform) } : undefined}
      className={cn('relative', isDragging && 'z-50 opacity-50')}
    >
      <button
        type="button"
        aria-label={`Dismiss the suggestion for ${job.customer_name}`}
        title="Dismiss this suggestion"
        disabled={busy}
        onPointerDown={stop}
        onClick={(e) => { stop(e); onDismiss(); }}
        className="absolute -right-1.5 -top-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full border bg-background text-muted-foreground shadow-sm hover:border-red-300 hover:bg-red-50 hover:text-red-600"
      >
        <X className="h-3 w-3" />
      </button>
      <div
        {...listeners}
        {...attributes}
        className="cursor-grab touch-none select-none rounded-md border border-dotted border-violet-400/80 bg-violet-50/40 px-2.5 py-2 hover:border-violet-500 active:cursor-grabbing"
        title={`Suggested, not saved${job.suggested_why ? ` (${job.suggested_why})` : ''}. Keep it, drag it to another day, or dismiss it.`}
      >
        <div className="flex items-center justify-between gap-2 pr-2">
          <JobName job={job} className="text-xs font-semibold" />
          <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-violet-100 px-1 py-px text-[9px] font-medium text-violet-800">
            <Sparkles className="h-2.5 w-2.5" />
            Suggested
          </span>
        </div>
        <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-muted-foreground">
          <MapPin className="h-3 w-3 shrink-0" />
          {job.address}
        </p>
        <p className="mt-1 flex items-center gap-1 truncate text-[11px] text-slate-800">
          <HardHat className="h-3 w-3 shrink-0" />
          {crew?.name ?? 'Crew'}
          {pm && <span className="truncate text-muted-foreground">· {pm.name}</span>}
        </p>
        <p className="mt-0.5 flex items-center gap-1 text-[11px] text-slate-800">
          <CalendarDays className="h-3 w-3 shrink-0" />
          {days} day{days > 1 ? 's' : ''}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1 empty:hidden">
          <ReadyCheckBadge job={job} small />
          <NoBuildDatesBadge windows={job.no_build_dates} small />
        </div>
        <button
          type="button"
          disabled={busy}
          onPointerDown={stop}
          onClick={(e) => { stop(e); onKeep(); }}
          className="mt-1.5 inline-flex items-center gap-1 rounded-md border border-violet-300 bg-white px-1.5 py-px text-[10px] font-medium text-violet-900 hover:bg-violet-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
        >
          <Check className="h-2.5 w-2.5" />
          Keep
        </button>
      </div>
    </div>
  );
}
