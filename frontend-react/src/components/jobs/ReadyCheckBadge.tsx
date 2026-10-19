import { useState } from 'react';
import { format, parseISO } from 'date-fns';
import { AlertTriangle, CheckCircle2, PauseCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Textarea } from '@/components/ui/textarea';
import { useReadyDecision } from '@/api/jobs';
import { cn } from '@/lib/utils';
import type { Job } from '@/types';

const LOOK = {
  flagged: {
    chip: 'bg-amber-50 text-amber-900 border-amber-300 hover:bg-amber-100',
    icon: AlertTriangle,
    lead: 'Check notes',
    title: 'Something in the notes may hold this job up',
  },
  hold: {
    chip: 'bg-red-50 text-red-800 border-red-300 hover:bg-red-100',
    icon: PauseCircle,
    lead: 'On hold',
    title: 'On hold, not ready to schedule',
  },
  ok: {
    chip: 'bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100',
    icon: CheckCircle2,
    lead: 'OK to schedule',
    title: 'Checked and OK to schedule',
  },
} as const;

/** Things that keep a job from being sent to JobNimbus: an unanswered flag or a hold. */
export function readyBlocked(job: Job) {
  return job.ready_status === 'flagged' || job.ready_status === 'hold';
}

export function readyIssue(job: Job) {
  const flags = job.ready_flags ?? [];
  if (flags.length === 0) return '';
  return flags.length === 1 ? flags[0].issue : `${flags[0].issue} +${flags.length - 1}`;
}

/**
 * Ready check chip. Amber = the notes say something might stop the build and nobody has
 * answered yet; red = someone put it on hold; green = someone said it's fine. Clicking it
 * opens the flags with the exact note each came from, plus OK / Hold buttons.
 */
export function ReadyCheckBadge({ job, small = false }: { job: Job; small?: boolean }) {
  const status = job.ready_status;
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const decide = useReadyDecision();
  if (status !== 'flagged' && status !== 'hold' && status !== 'ok') return null;
  // A green chip is noise on the tight Weekly Plan rows; show it only where there's room
  if (status === 'ok' && small) return null;

  const look = LOOK[status];
  const Icon = look.icon;
  const flags = job.ready_flags ?? [];

  const answer = async (decision: 'ok' | 'hold') => {
    try {
      const res = await decide.mutateAsync({ id: job.id, decision, note: note.trim() || undefined });
      setOpen(false);
      setNote('');
      const what = decision === 'ok' ? 'OK to schedule' : 'On hold';
      if (res.pushed_to_jn) toast.success(`${job.customer_name}: ${what}. Noted in JobNimbus.`);
      else toast.warning(`${job.customer_name}: ${what}. Saved here, but the JobNimbus note didn't go through.`);
    } catch {
      toast.error(`Couldn't save the answer for ${job.customer_name}. Try again.`);
    }
  };

  const stop = (e: React.SyntheticEvent) => e.stopPropagation();

  return (
    <span onPointerDown={stop} onClick={stop} className="inline-flex max-w-full">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          className={cn(
            'inline-flex max-w-full items-center gap-1 rounded-md border font-medium transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
            small ? 'h-[18px] px-1 text-[9px]' : 'h-6 px-1.5 text-[11px]',
            look.chip,
          )}
          aria-label={`${look.lead}: ${readyIssue(job) || 'see details'}`}
        >
          <Icon className={cn('shrink-0', small ? 'h-2.5 w-2.5' : 'h-3 w-3')} />
          <span className="truncate">
            {status === 'ok' ? look.lead : `${look.lead}: ${readyIssue(job)}`}
          </span>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          className="w-80 gap-3 p-3"
          onPointerDown={stop}
          onClick={stop}
        >
          <p className="text-sm font-semibold leading-snug">{look.title}</p>

          {flags.length > 0 && (
            <ul className="space-y-2.5">
              {flags.map((f, i) => (
                <li key={i} className="space-y-0.5">
                  <p className="text-[13px] font-medium leading-snug">{f.issue}</p>
                  {f.quote && (
                    <p className="text-xs leading-snug text-muted-foreground">“{f.quote}”</p>
                  )}
                  {f.source && <p className="text-[11px] text-muted-foreground/80">{f.source}</p>}
                </li>
              ))}
            </ul>
          )}

          {(status === 'ok' || status === 'hold') && job.ready_decision_by && (
            <p className="rounded-md bg-muted px-2 py-1.5 text-xs leading-snug">
              {status === 'ok' ? 'Marked OK' : 'Put on hold'} by {job.ready_decision_by}
              {job.ready_decision_at && ` on ${format(parseISO(job.ready_decision_at + 'Z'), 'MMM d')}`}
              {job.ready_decision_note && <span className="block text-muted-foreground">“{job.ready_decision_note}”</span>}
            </p>
          )}

          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note (optional), like: colors are white, confirmed with customer"
            className="min-h-[60px] text-xs"
            onKeyDown={stop}
          />
          <div className="flex gap-2">
            <Button size="sm" className="flex-1" disabled={decide.isPending} onClick={() => answer('ok')}>
              OK to schedule
            </Button>
            <Button size="sm" variant="outline" className="flex-1" disabled={decide.isPending}
              onClick={() => answer('hold')}>
              Keep on hold
            </Button>
          </div>
          <p className="text-[11px] leading-snug text-muted-foreground">
            Your answer is saved as a note on the job in JobNimbus.
          </p>
        </PopoverContent>
      </Popover>
    </span>
  );
}
