import { useState } from 'react';
import { format, addDays } from 'date-fns';
import { CalendarClock } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useMoveBooking } from '@/api/schedule';
import type { Job } from '@/types';

const REASONS = ['Weather', 'Customer asked', 'Crew', 'Materials', 'Other'];

/**
 * Move a build booked in JobNimbus to a new day, in one step: the work order comes off Pending Start
 * (which stops the old "you're on the calendar" messages), then it's booked again on the new day with
 * the same crew and PM, so the customer gets the Build Day email and text with the new date.
 */
export function MoveBookingButton({ job }: { job: Job }) {
  const [open, setOpen] = useState(false);
  const [day, setDay] = useState('');
  const [reason, setReason] = useState('Weather');
  const move = useMoveBooking();
  const stop = (e: React.SyntheticEvent) => e.stopPropagation();
  const tomorrow = format(addDays(new Date(), 1), 'yyyy-MM-dd');

  const go = async () => {
    try {
      const res = await move.mutateAsync({ job_id: job.id, new_date: day, reason });
      if (res.status === 'booked') {
        toast.success(`${job.customer_name} moved to ${format(new Date(day + 'T12:00'), 'EEE, MMM d')}. The customer gets the new date.`);
        setOpen(false);
      } else {
        toast.error(`${job.customer_name} wasn't moved: ${res.reason}`);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Couldn't reach JobNimbus. Check the job there before trying again.");
    }
  };

  return (
    <span onPointerDown={stop} onClick={stop} className="inline-flex">
      <Popover open={open} onOpenChange={(v) => { if (!move.isPending) { setOpen(v); if (v) setDay(''); } }}>
        <PopoverTrigger
          className="mt-1 inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-1.5 py-px text-[10px] font-medium text-slate-700 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <CalendarClock className="h-2.5 w-2.5" />
          Move
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72 gap-3 p-3" onPointerDown={stop} onClick={stop}>
          <div>
            <p className="text-sm font-semibold leading-snug">Move {job.customer_name}</p>
            <p className="text-[11px] leading-snug text-muted-foreground">
              Takes it off the JobNimbus calendar and books the new day with the same crew. The customer gets the
              Build Day email and text with the new date. To pull it without a new day, use Not Built.
            </p>
          </div>
          <label className="space-y-1 text-xs">
            <span className="font-medium">New day</span>
            <Input type="date" min={tomorrow} value={day} onChange={(e) => setDay(e.target.value)} onKeyDown={stop}
              className="h-8 text-xs" />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">Why</span>
            <select value={reason} onChange={(e) => setReason(e.target.value)}
              className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
              {REASONS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </label>
          <Button size="sm" onClick={go} disabled={!day || move.isPending}>
            {move.isPending ? 'Moving…' : 'Move it'}
          </Button>
        </PopoverContent>
      </Popover>
    </span>
  );
}
