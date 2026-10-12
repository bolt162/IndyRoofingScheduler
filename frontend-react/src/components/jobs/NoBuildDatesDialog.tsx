import { useState } from 'react';
import { format } from 'date-fns';
import { CalendarX, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { useSetNoBuildDates } from '@/api/jobs';
import { describeNoBuild } from '@/lib/no-build';
import type { Job, NoBuildWindow } from '@/types';

/**
 * Add or remove a job's No-Build Dates. Each add/remove saves right away (the
 * whole list is sent), so there's no separate Save step to forget.
 */
export function NoBuildDatesDialog({
  job,
  open,
  onOpenChange,
}: {
  job: Job;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const today = format(new Date(), 'yyyy-MM-dd');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [reason, setReason] = useState('');
  const setNoBuildDates = useSetNoBuildDates();
  const windows = job.no_build_dates ?? [];

  const save = (next: NoBuildWindow[], success: string, onDone?: () => void) => {
    setNoBuildDates.mutate(
      { id: job.id, windows: next },
      {
        onSuccess: (result) => {
          toast.success(success);
          if (result.scheduled_conflict) {
            toast.warning(result.scheduled_conflict, { duration: 12000 });
          }
          onDone?.();
        },
        onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to save No-Build Dates'),
      },
    );
  };

  const handleAdd = () => {
    if (!start || !end || end < start) return;
    const added: NoBuildWindow = { start, end, reason: reason.trim() || null };
    save([...windows, added], `No-Build Dates added: ${describeNoBuild(added)}`, () => {
      setStart('');
      setEnd('');
      setReason('');
    });
  };

  const handleRemove = (w: NoBuildWindow) => {
    save(
      windows.filter((x) => x !== w),
      `No-Build Dates removed: ${describeNoBuild(w)}`,
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarX className="h-4 w-4 text-violet-700" />
            No-Build Dates
          </DialogTitle>
          <DialogDescription>
            Dates {job.customer_name} asked us not to build. Scoring leaves the job out on
            these days, and the Weekly Plan asks before anyone drags it onto one. Dates clear
            themselves once they pass.
          </DialogDescription>
        </DialogHeader>

        {windows.length > 0 && (
          <div className="space-y-1.5">
            {windows.map((w) => (
              <div
                key={`${w.start}-${w.end}`}
                className="flex items-center justify-between gap-2 rounded border border-violet-200 bg-violet-50 px-3 py-2 text-sm"
              >
                <span className="text-violet-900">{describeNoBuild(w)}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-xs text-muted-foreground hover:text-red-600"
                  disabled={setNoBuildDates.isPending}
                  onClick={() => handleRemove(w)}
                >
                  <Trash2 className="h-3 w-3" />
                  Remove
                </Button>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="nb-start">From</Label>
              <Input
                id="nb-start"
                type="date"
                value={start}
                min={today}
                onChange={(e) => {
                  setStart(e.target.value);
                  // Most windows are a single event: default the end to the start
                  if (!end || end < e.target.value) setEnd(e.target.value);
                }}
              />
            </div>
            <div>
              <Label htmlFor="nb-end">To</Label>
              <Input
                id="nb-end"
                type="date"
                value={end}
                min={start || today}
                onChange={(e) => setEnd(e.target.value)}
              />
            </div>
          </div>
          <div>
            <Label htmlFor="nb-reason">Reason (optional)</Label>
            <Input
              id="nb-reason"
              placeholder="e.g., Family wedding"
              value={reason}
              maxLength={200}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          {start && end && end < start && (
            <p className="text-xs text-red-600">The "To" date is before the "From" date.</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Done</Button>
          <Button
            onClick={handleAdd}
            disabled={!start || !end || end < start || setNoBuildDates.isPending}
            className="bg-violet-700 hover:bg-violet-800"
          >
            {setNoBuildDates.isPending ? 'Saving...' : 'Add No-Build Dates'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
