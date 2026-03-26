import { useState } from 'react';
import { differenceInDays, parseISO, format } from 'date-fns';
import {
  MapPin, Calendar, DollarSign, Layers, Users, Hash, Star, CheckCircle,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip';
import { MustBuildBadge } from './MustBuildBadge';
import { DurationFlag } from './DurationFlag';
import { WeatherBadge } from './WeatherBadge';
import { useSetMustBuild, useUpdateJob } from '@/api/jobs';
import { MATERIAL_LABELS } from '@/types';
import { cn } from '@/lib/utils';
import type { Job } from '@/types';

const PAYMENT_COLORS: Record<string, string> = {
  cash: 'bg-green-100 text-green-800',
  finance: 'bg-blue-100 text-blue-800',
  insurance: 'bg-gray-100 text-gray-700',
};

export function JobCard({ job, compact = false }: { job: Job; compact?: boolean }) {
  const daysInQueue = job.date_entered
    ? differenceInDays(new Date(), parseISO(job.date_entered))
    : null;

  // Must-Build dialog state
  const [mustBuildOpen, setMustBuildOpen] = useState(false);
  const [mbDeadline, setMbDeadline] = useState('');
  const [mbReason, setMbReason] = useState('');
  const setMustBuild = useSetMustBuild();

  // Confirm Duration dialog state
  const [confirmDurOpen, setConfirmDurOpen] = useState(false);
  const [confirmedDays, setConfirmedDays] = useState(String(job.duration_days));
  const updateJob = useUpdateJob();

  const handleSetMustBuild = () => {
    if (!mbDeadline) return;
    setMustBuild.mutate(
      { id: job.id, deadline: mbDeadline, reason: mbReason || undefined },
      { onSuccess: () => setMustBuildOpen(false) },
    );
  };

  const handleConfirmDuration = () => {
    const days = parseInt(confirmedDays, 10);
    if (!days || days < 1) return;
    updateJob.mutate(
      { id: job.id, update: { duration_days: days, duration_confirmed: true } },
      { onSuccess: () => setConfirmDurOpen(false) },
    );
  };

  // Check if multi_day_signal exists in AI scan (informational only)
  let multiDayHint = false;
  if (job.ai_note_scan_result) {
    try {
      const scan = JSON.parse(job.ai_note_scan_result);
      multiDayHint = scan.multi_day_signal === true;
    } catch { /* ignore */ }
  }

  return (
    <>
      <Card
        className={cn(
          'transition-shadow hover:shadow-md',
          job.must_build && 'ring-2 ring-red-500/50 bg-red-50/30',
          job.crew_requirement_flag && 'border-l-4 border-l-orange-500',
        )}
      >
        <CardContent className={cn('space-y-2', compact ? 'p-3' : 'p-4')}>
          {/* Row 1: Name + Score + Flags */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p className={cn('font-semibold truncate', compact ? 'text-sm' : 'text-base')}>
                {job.customer_name}
              </p>
              <p className="text-xs text-muted-foreground flex items-center gap-1 truncate">
                <MapPin className="h-3 w-3 shrink-0" />
                {job.address}
              </p>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge variant="outline" className="font-mono text-xs tabular-nums cursor-help">
                      {job.score.toFixed(1)}
                    </Badge>
                  </TooltipTrigger>
                  {job.score_explanation && (
                    <TooltipContent side="left" className="max-w-xs">
                      <p className="text-[10px] font-mono whitespace-pre-wrap">
                        {job.score_explanation.split('; ').join('\n')}
                      </p>
                    </TooltipContent>
                  )}
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>

          {/* Row 2: Flags */}
          <div className="flex flex-wrap gap-1.5">
            {job.must_build && (
              <MustBuildBadge deadline={job.must_build_deadline} reason={job.must_build_reason} />
            )}
            {job.crew_requirement_flag && (
              <Badge variant="outline" className="gap-1 text-[10px] bg-orange-100 text-orange-800">
                <Users className="h-3 w-3" />
                Crew Req
              </Badge>
            )}
            {job.standalone_rule && (
              <Badge variant="outline" className="text-[10px] bg-amber-100 text-amber-800">
                Standalone
              </Badge>
            )}
            {job.is_multi_day && (
              <Badge variant="outline" className="text-[10px] bg-purple-100 text-purple-800">
                Multi-Day ({job.multi_day_current}/{job.duration_days})
              </Badge>
            )}
            {/* Informational hint from AI scan — not the actual multi-day flag */}
            {!job.is_multi_day && multiDayHint && (
              <Badge variant="outline" className="text-[10px] bg-purple-50 text-purple-600 border-dashed">
                ⚠ AI: Likely Multi-Day
              </Badge>
            )}
            {job.rescheduled_count > 0 && (
              <Badge variant="outline" className="text-[10px] bg-red-50 text-red-700">
                <Hash className="h-3 w-3" />
                Resched ×{job.rescheduled_count}
              </Badge>
            )}
            <WeatherBadge status={job.weather_status} detail={job.weather_detail} />
          </div>

          {/* Row 3: Details grid */}
          {!compact && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <Layers className="h-3 w-3" />
                {job.material_type ? MATERIAL_LABELS[job.material_type] ?? job.material_type : '—'}
                {job.square_footage ? ` · ${job.square_footage} sq` : ''}
              </div>
              <div className="flex items-center gap-1">
                <DollarSign className="h-3 w-3" />
                <span className={cn(
                  'px-1 rounded text-[10px] font-medium',
                  job.payment_type ? PAYMENT_COLORS[job.payment_type] ?? '' : '',
                )}>
                  {job.payment_type ?? '—'}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {daysInQueue !== null ? `${daysInQueue}d in queue` : '—'}
              </div>
              <DurationFlag
                tier={job.duration_tier}
                days={job.duration_days}
                confirmed={job.duration_confirmed}
              />
            </div>
          )}

          {/* Row 4: Trade info + JN note preview */}
          {!compact && (
            <div className="flex items-center gap-2 text-xs">
              <Badge variant="secondary" className="text-[10px]">
                {job.primary_trade ?? 'Roofing'}
              </Badge>
              {job.secondary_trades?.map((t) => (
                <Badge key={t} variant="outline" className="text-[10px]">
                  {t}
                </Badge>
              ))}
            </div>
          )}

          {/* Row 5: Duration hint from AI scan (spec §4.3 line 191) */}
          {!compact && job.ai_note_scan_result && (
            <DurationHint scanResult={job.ai_note_scan_result} />
          )}

          {/* Row 6: JN Note Preview — raw note from JN (spec 9.4 line 411) */}
          {!compact && job.jn_notes_raw && (
            <NotePreview notesRaw={job.jn_notes_raw} />
          )}

          {/* Row 6: Action buttons — only for To Schedule jobs */}
          {!compact && job.bucket === 'to_schedule' && (
            <div className="flex flex-wrap gap-1.5 pt-1 border-t">
              {/* Must-Build toggle */}
              {!job.must_build && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 text-[10px] gap-1 text-red-700 hover:bg-red-50"
                  onClick={() => setMustBuildOpen(true)}
                >
                  <Star className="h-3 w-3" />
                  Set Must-Build
                </Button>
              )}

              {/* Confirm Duration — show when duration is unconfirmed */}
              {!job.duration_confirmed && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 text-[10px] gap-1 text-yellow-700 hover:bg-yellow-50"
                  onClick={() => {
                    setConfirmedDays(String(job.duration_days));
                    setConfirmDurOpen(true);
                  }}
                >
                  <CheckCircle className="h-3 w-3" />
                  Confirm Duration
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Must-Build Dialog */}
      <Dialog open={mustBuildOpen} onOpenChange={setMustBuildOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Set Must-Build</DialogTitle>
            <DialogDescription>
              Flag {job.customer_name} as Must-Build. A deadline is required — the system
              uses it to calculate urgency and anchor this job first in the weekly plan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label htmlFor="mb-deadline">Deadline Date *</Label>
              <Input
                id="mb-deadline"
                type="date"
                value={mbDeadline}
                onChange={(e) => setMbDeadline(e.target.value)}
                min={format(new Date(), 'yyyy-MM-dd')}
              />
            </div>
            <div>
              <Label htmlFor="mb-reason">Reason (optional)</Label>
              <Input
                id="mb-reason"
                placeholder="e.g., Real estate closing, customer commitment"
                value={mbReason}
                onChange={(e) => setMbReason(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMustBuildOpen(false)}>Cancel</Button>
            <Button
              onClick={handleSetMustBuild}
              disabled={!mbDeadline || setMustBuild.isPending}
              className="bg-red-600 hover:bg-red-700"
            >
              {setMustBuild.isPending ? 'Saving...' : 'Flag as Must-Build'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm Duration Dialog */}
      <Dialog open={confirmDurOpen} onOpenChange={setConfirmDurOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm Duration</DialogTitle>
            <DialogDescription>
              Confirm or adjust the build duration for {job.customer_name}.
              {job.duration_source && (
                <span className="block mt-1 text-xs text-muted-foreground">
                  Current source: {job.duration_source}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label htmlFor="dur-days">Duration (days)</Label>
              <Input
                id="dur-days"
                type="number"
                min="1"
                max="14"
                value={confirmedDays}
                onChange={(e) => setConfirmedDays(e.target.value)}
              />
            </div>
            {job.duration_tier === 'tier_3' && (
              <p className="text-xs text-red-600 font-medium">
                ⚠ Tier 3 job (61+ sq) — duration confirmation is required before this job can be finalized.
              </p>
            )}
            {job.duration_tier === 'low_slope' && (
              <p className="text-xs text-red-600 font-medium">
                ⚠ Low slope job — manual duration and crew confirmation required.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDurOpen(false)}>Cancel</Button>
            <Button
              onClick={handleConfirmDuration}
              disabled={!confirmedDays || parseInt(confirmedDays) < 1 || updateJob.isPending}
            >
              {updateJob.isPending ? 'Saving...' : 'Confirm Duration'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * Duration hint from AI scan — spec §4.3 line 191:
 * "Note from [date] references [quote] — duration set to [X days], Unconfirmed."
 */
function DurationHint({ scanResult }: { scanResult: string }) {
  try {
    const scan = JSON.parse(scanResult);
    if (!scan.duration_hint || !scan.duration_reason) return null;
    return (
      <p className="text-[10px] text-yellow-700 bg-yellow-50 rounded px-2 py-1 italic">
        ⏱ AI: {scan.duration_reason} — duration set to {scan.duration_hint}d, Unconfirmed.
        Please validate before finalizing schedule.
      </p>
    );
  } catch {
    return null;
  }
}

/**
 * One-line JN note preview — spec 9.4 line 411:
 * "One-line summary of most relevant scheduler-facing note"
 * Shows truncated raw JN notes/description.
 */
function NotePreview({ notesRaw }: { notesRaw: string }) {
  // Strip the "[Job Description] " or "[Note] " prefix for display
  let preview = notesRaw.trim();
  if (preview.startsWith('[Job Description] ')) {
    preview = preview.slice(18);
  } else if (preview.startsWith('[Note] ')) {
    preview = preview.slice(7);
  }
  // Take only the first segment (before ---) and truncate
  const firstSegment = preview.split('\n---\n')[0].trim();
  if (!firstSegment) return null;
  return (
    <p className="text-[10px] text-muted-foreground truncate italic">
      📝 {firstSegment}
    </p>
  );
}
