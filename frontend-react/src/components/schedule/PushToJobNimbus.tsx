import { useState } from 'react';
import { format, parseISO } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, CheckCircle2, CircleSlash, Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { usePushPreview, usePushToJobNimbus } from '@/api/schedule';
import { cn } from '@/lib/utils';
import type { PushResult } from '@/types';

const day = (iso: string) => format(parseISO(iso), 'EEE, MMM d');

/**
 * "Push to JobNimbus": books every planned job that's ready, doing Greg's steps in JobNimbus
 * (work order date, crew and Luke, Pending Start, job Pending Start Date, rep note, Build Block,
 * prep tasks). Moving the work order to Pending Start texts and emails the customer, so this
 * always asks first and lists exactly who gets booked.
 */
export function PushToJobNimbus({ plannedCount }: { plannedCount: number }) {
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<PushResult[] | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const { data: preview, isLoading } = usePushPreview(open);
  const push = usePushToJobNimbus();

  const ready = preview?.items.filter((i) => i.ready) ?? [];
  const skipped = preview?.items.filter((i) => !i.ready) ?? [];

  const busy = progress !== null;

  const close = (next: boolean) => {
    if (busy) return;
    setOpen(next);
    if (!next) setResults(null);
  };

  // One job per request: each answer arrives in seconds, so a big week never outlasts the browser,
  // and the list shows exactly which ones made it if anything stops partway.
  const send = async () => {
    const out: PushResult[] = [];
    let stopped: string | null = null;
    setProgress({ done: 0, total: ready.length });
    for (const item of ready) {
      try {
        const res = await push.mutateAsync([item.job_id]);
        out.push(...res.results);
        if (res.results.some((r) => r.jn_error)) {
          stopped = 'JobNimbus stopped answering, so the rest were not sent. Push again in a few minutes to finish.';
          break;
        }
      } catch (err: any) {
        stopped = err?.response?.data?.detail
          ?? `Lost the connection while booking ${item.customer_name}. Push again to finish; nothing is sent twice.`;
        break;
      }
      setProgress({ done: out.length, total: ready.length });
    }
    setProgress(null);
    setResults(out);
    const booked = out.filter((r) => r.status === 'booked').length;
    const failed = out.filter((r) => r.status === 'failed').length;
    if (stopped) toast.error(stopped);
    else if (failed) toast.error(`${failed} job${failed > 1 ? 's' : ''} didn't finish. See why below.`);
    else toast.success(`Booked ${booked} job${booked === 1 ? '' : 's'} in JobNimbus`);
  };

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)} disabled={plannedCount === 0}>
        <Send className="mr-1 h-4 w-4" />
        Push to JobNimbus{plannedCount > 0 && ` (${plannedCount})`}
      </Button>

      <Dialog open={open} onOpenChange={close}>
        <DialogContent className="sm:max-w-lg" showCloseButton={!busy}>
          <DialogHeader>
            <DialogTitle>{results ? 'Sent to JobNimbus' : 'Book these jobs in JobNimbus?'}</DialogTitle>
            {!results && (
              <DialogDescription>
                Each job gets its date, crew and Luke on the work order, moves to Pending Start, and the
                rep gets a note and a Build Block. Customers get the Build Day email and text right away.
              </DialogDescription>
            )}
          </DialogHeader>

          {preview && !preview.can_book && !results && (
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              Only the office, operations or owners can book jobs in JobNimbus. You can still see the list.
            </p>
          )}
          {preview?.mode === 'test' && !results && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">
              Test mode: only the test job is sent. Everything else stays planned.
            </p>
          )}

          {results ? (
            <ul className="space-y-2">
              {results.map((r) => (
                <li key={r.job_id} className="flex items-start gap-2 text-xs">
                  {r.status === 'booked' ? (
                    <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0 text-emerald-600" />
                  ) : r.status === 'failed' ? (
                    <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0 text-red-600" />
                  ) : (
                    <CircleSlash className="mt-px h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  )}
                  <span className="min-w-0">
                    <span className="font-medium">{r.customer_name}</span>
                    <span className="text-muted-foreground">
                      {r.status === 'booked' ? ` booked${r.work_order ? ` on ${r.work_order}` : ''}` : ` · ${r.reason}`}
                    </span>
                  </span>
                </li>
              ))}
              <li className="pt-1 text-[11px] text-muted-foreground">
                Booked jobs turn into gray Booked cards after the next JobNimbus sync (within 15 minutes).
              </li>
            </ul>
          ) : isLoading ? (
            <p className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Checking the plan…
            </p>
          ) : (
            <div className="space-y-4">
              <section>
                <h4 className="mb-1.5 text-xs font-semibold">Will be booked ({ready.length})</h4>
                {ready.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Nothing is ready yet. The list below says what each job needs.</p>
                ) : (
                  <ul className="divide-y rounded-md border">
                    {ready.map((i) => (
                      <li key={i.job_id} className="grid grid-cols-[1fr_auto] gap-x-3 px-3 py-1.5 text-xs">
                        <span className="truncate font-medium">{i.customer_name}</span>
                        <span className="tabular-nums text-muted-foreground">{day(i.planned_date)}</span>
                        <span className="col-span-2 truncate text-[11px] text-muted-foreground">
                          {i.crew} · {i.pm}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              {skipped.length > 0 && (
                <section>
                  <h4 className="mb-1.5 text-xs font-semibold text-muted-foreground">Staying planned ({skipped.length})</h4>
                  <ul className="max-h-48 space-y-1 overflow-y-auto pr-1">
                    {skipped.map((i) => (
                      <li key={i.job_id} className="text-xs">
                        <span className="font-medium">{i.customer_name}</span>
                        <span className="text-muted-foreground"> · {day(i.planned_date)} · {i.reason}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}

          <DialogFooter>
            {results ? (
              <Button onClick={() => close(false)}>Done</Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => close(false)} disabled={busy}>Cancel</Button>
                <Button onClick={send} disabled={busy || ready.length === 0 || !preview?.can_book}
                        className={cn(busy && 'cursor-wait')}>
                  {progress ? (
                    <><Loader2 className="mr-1 h-4 w-4 animate-spin" /> Booking {progress.done + 1} of {progress.total}…</>
                  ) : (
                    <>Book {ready.length} in JobNimbus</>
                  )}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
