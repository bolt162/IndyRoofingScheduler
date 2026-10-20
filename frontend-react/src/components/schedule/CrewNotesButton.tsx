import { useMemo, useState } from 'react';
import { ClipboardList, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useApproveCrewNotes } from '@/api/jobs';
import { useSettings } from '@/api/settings';
import { cn } from '@/lib/utils';
import type { Job } from '@/types';

/** Crew notes are on unless someone switched them off in Settings > System. */
export function useCrewNotesEnabled() {
  const { data: settings } = useSettings();
  const v = (settings?.crew_notes_enabled?.value ?? 'true').toLowerCase();
  return !['false', 'off', '0', 'no'].includes(v);
}

/**
 * Suggested notes for the crew's work order (gutter scope, plus install instructions found in the notes).
 * Nothing reaches the crew until someone approves here; approved lines are added when the job is pushed.
 */
export function CrewNotesButton({ job }: { job: Job }) {
  const on = useCrewNotesEnabled();
  const approve = useApproveCrewNotes();
  const [open, setOpen] = useState(false);
  const suggestions = job.crew_note_suggestions ?? [];
  const approved = job.crew_notes_approved ?? [];
  const reviewed = !!job.crew_notes_at;

  // Everything to choose from: suggestions first, then lines someone added by hand earlier
  const options = useMemo(() => {
    const texts = suggestions.map((s) => s.text);
    return [...suggestions, ...approved.filter((a) => !texts.includes(a)).map((text) => ({ text, kind: 'added' as const }))];
  }, [suggestions, approved]);
  const [picked, setPicked] = useState<string[]>([]);
  const [extra, setExtra] = useState('');

  if (!on || (options.length === 0 && !reviewed)) return null;

  const openUp = (next: boolean) => {
    if (next) {
      // First look: everything suggested is ticked, so approving is one click
      setPicked(reviewed ? approved : options.map((o) => o.text));
      setExtra('');
    }
    setOpen(next);
  };

  const save = async () => {
    const lines = [...picked, ...(extra.trim() ? [extra.trim()] : [])];
    try {
      await approve.mutateAsync({ id: job.id, lines });
      setOpen(false);
      toast.success(lines.length
        ? `Approved ${lines.length} crew note${lines.length > 1 ? 's' : ''} for ${job.customer_name}`
        : `No crew notes for ${job.customer_name}`);
    } catch {
      toast.error("Couldn't save the crew notes. Try again.");
    }
  };

  const stop = (e: React.SyntheticEvent) => e.stopPropagation();
  const label = reviewed
    ? approved.length ? `Crew notes: ${approved.length} approved` : 'Crew notes: none'
    : `Crew notes: review ${options.length}`;

  return (
    <span onPointerDown={stop} onClick={stop} className="inline-flex max-w-full">
      <Popover open={open} onOpenChange={openUp}>
        <PopoverTrigger
          className={cn(
            'mt-1 inline-flex max-w-full items-center gap-1 rounded-md border px-1.5 py-px text-[10px] font-medium transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            reviewed ? 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
              : 'border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100',
          )}
        >
          <ClipboardList className="h-2.5 w-2.5 shrink-0" />
          <span className="truncate">{label}</span>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80 gap-3 p-3" onPointerDown={stop} onClick={stop}>
          <div>
            <p className="text-sm font-semibold leading-snug">Notes for the crew</p>
            <p className="text-[11px] leading-snug text-muted-foreground">
              Ticked lines go on the work order the crew reads when this job is pushed to JobNimbus.
            </p>
          </div>
          <ul className="space-y-2.5">
            {options.map((o) => {
              const on_ = picked.includes(o.text);
              return (
                <li key={o.text}>
                  <label className="flex cursor-pointer items-start gap-2">
                    <Checkbox
                      checked={on_}
                      onCheckedChange={(v) => setPicked((p) => (v ? [...p, o.text] : p.filter((t) => t !== o.text)))}
                      className="mt-0.5"
                    />
                    <span className="min-w-0 space-y-0.5">
                      <span className="block text-[13px] leading-snug">{o.text}</span>
                      {'quote' in o && o.quote && (
                        <span className="block text-xs leading-snug text-muted-foreground">“{o.quote}”</span>
                      )}
                      {'source' in o && o.source && (
                        <span className="block text-[11px] text-muted-foreground/80">{o.source}</span>
                      )}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
          <div className="flex items-center gap-1.5">
            <Plus className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <Input
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
              onKeyDown={stop}
              placeholder="Add a line for the crew (optional)"
              className="h-8 text-xs"
              maxLength={200}
            />
          </div>
          <Button size="sm" onClick={save} disabled={approve.isPending}>
            {picked.length + (extra.trim() ? 1 : 0) > 0 ? 'Approve' : 'No crew notes for this job'}
          </Button>
        </PopoverContent>
      </Popover>
    </span>
  );
}
