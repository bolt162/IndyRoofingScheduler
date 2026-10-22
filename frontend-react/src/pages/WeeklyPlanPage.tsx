import { useMemo, useState } from 'react';
import { addDays, format, isToday, parseISO } from 'date-fns';
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  TouchSensor,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { toast } from 'sonner';
import {
  ChevronLeft, ChevronRight, Check, Sparkles, X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { DayColumn } from '@/components/schedule/DayColumn';
import { UnassignedJobRow } from '@/components/schedule/UnassignedJobRow';
import { PushToJobNimbus } from '@/components/schedule/PushToJobNimbus';
import { useJobs, useReadyOpen, useUpdateJob } from '@/api/jobs';
import {
  useSchedulePlans, useConfirmPlan, useSuggestBuilds, useKeepSuggestions, useClearSuggestions,
} from '@/api/schedule';
import { usePMs } from '@/api/settings';
import { useUIStore } from '@/stores/ui-store';
import { cn } from '@/lib/utils';
import { describeNoBuild, noBuildConflict } from '@/lib/no-build';
import { ReadyCheckBadge, readyBlocked, readyIssue } from '@/components/jobs/ReadyCheckBadge';
import type { Job } from '@/types';

/** Still waiting in the queue, so a day can be picked for it here. */
const PUSH_STEPS = ['work_order', 'work_order_status', 'job_status', 'rep_note', 'build_block', 'tasks'];

/** A push that told the customer but stopped before the last step; it stays on the plan so Push can finish it. */
function pushInProgress(job: Job) {
  const s = job.jn_push_steps ?? {};
  return !!s.work_order_status && !PUSH_STEPS.every((k) => s[k]);
}

/** Gutters or siding after the main trade that JobNimbus has booked (its work order is at Pending Start). */
function followUpBooked(job: Job) {
  return !!job.follow_up_trade && (job.jn_work_orders ?? []).some((w) => w.status.trim().toLowerCase() === 'pending start');
}

/** Same rule as the Push to JobNimbus count (jn_booking.candidates), so every job it counts shows here. */
function isPlannable(job: Job) {
  return job.bucket === 'to_schedule' || job.bucket === 'not_built' || !!job.follow_up_trade || pushInProgress(job);
}

export function WeeklyPlanPage() {
  const { selectedWeekStart, nextWeek, prevWeek, selectedPMIds, togglePM } = useUIStore();
  const { data: allJobs } = useJobs();
  const { data: readyOpen } = useReadyOpen();
  const { data: plans } = useSchedulePlans();
  const { data: pms } = usePMs();
  const updateJob = useUpdateJob();
  const confirmPlan = useConfirmPlan();
  const suggestBuilds = useSuggestBuilds();
  const keepSuggestions = useKeepSuggestions();
  const clearSuggestions = useClearSuggestions();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    // Touch sensor with 200ms delay so tap scroll still works on mobile
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
  );

  // Mobile: toggle unassigned jobs panel
  const [unassignedOpenMobile, setUnassignedOpenMobile] = useState(false);

  // Build 7 days starting from Monday
  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(selectedWeekStart, i)),
    [selectedWeekStart]
  );

  // Active PMs
  const activePMs = useMemo(
    () => pms?.filter((p) => p.is_active) ?? [],
    [pms]
  );

  // Each day: builds JobNimbus has booked (its work order date is the truth), and days picked
  // here that haven't been sent to JobNimbus yet. Plans live apart from the booking so the
  // 15-minute JobNimbus sync never erases them.
  const daysByKey = useMemo(() => {
    const map: Record<string, { booked: Job[]; planned: Job[]; suggested: Job[] }> = {};
    weekDays.forEach((d) => {
      const key = format(d, 'yyyy-MM-dd');
      map[key] = {
        booked: (allJobs ?? []).filter(
          (j) => (j.bucket === 'scheduled' || followUpBooked(j)) && (j.jn_start_date ?? j.date_scheduled) === key,
        ),
        planned: (allJobs ?? []).filter((j) => j.planned_date === key && isPlannable(j)),
        suggested: (allJobs ?? []).filter((j) => j.suggested_date === key && !j.planned_date && isPlannable(j)),
      };
    });
    return map;
  }, [allJobs, weekDays]);

  // PM job counts per day: planned ones by the PM picked here, booked ones by the PM on the work order
  const pmJobCountsByDay = useMemo(() => {
    const norm = (s: string) => s.toLowerCase().replace(/\s+/g, ' ').trim();
    const result: Record<string, Record<number, number>> = {};
    for (const [day, { booked, planned }] of Object.entries(daysByKey)) {
      result[day] = {};
      const add = (pmId: number | undefined | null) => {
        if (pmId) result[day][pmId] = (result[day][pmId] ?? 0) + 1;
      };
      planned.forEach((j) => add(j.planned_pm_id));
      booked.forEach((j) => {
        const pm = j.jn_pm ? activePMs.find((p) => norm(p.name) === norm(j.jn_pm!)
          || norm(j.jn_pm!).startsWith(norm(p.name))) : undefined;
        add(pm?.id);
      });
    }
    return result;
  }, [daysByKey, activePMs]);

  // Unassigned jobs (To Schedule bucket, and gutters / siding waiting after the main trade; not planned yet, sorted by score)
  const unassignedJobs = useMemo(
    () =>
      (allJobs ?? [])
        .filter((j) => (j.bucket === 'to_schedule' || (!!j.follow_up_trade && !followUpBooked(j)))
          && !j.planned_date && !j.suggested_date)
        .sort((a, b) => b.score - a.score),
    [allJobs]
  );

  // Every planned job on any week waits for Push to JobNimbus
  const plannedCount = useMemo(
    () => (allJobs ?? []).filter((j) => j.planned_date && isPlannable(j)).length,
    [allJobs]
  );

  const weekKey = format(selectedWeekStart, 'yyyy-MM-dd');
  const weekSuggested = useMemo(
    () => Object.values(daysByKey).reduce((n, d) => n + d.suggested.length, 0),
    [daysByKey],
  );

  const handleSuggest = async (kind: 'roofs' | 'gutters' | 'siding') => {
    try {
      const res = await suggestBuilds.mutateAsync({
        week_start: weekKey,
        kind,
        ...(selectedPMIds.length ? { pm_ids: selectedPMIds } : {}),
      });
      const n = res.suggested.length;
      const word = kind === 'roofs' ? 'roof' : kind === 'gutters' ? 'gutter' : 'siding';
      const what = kind === 'roofs' ? 'roof' : `${word} job`;
      if (n === 0) toast.info(res.reason ?? `No open ${word} slots to fill this week.`);
      else toast.success(`Suggested ${n} ${what}${n > 1 ? 's' : ''}. Nothing is saved until you keep them.`);
    } catch {
      toast.error("Couldn't make suggestions. Try again.");
    }
  };
  const suggesting = suggestBuilds.isPending ? suggestBuilds.variables?.kind : undefined;

  // Draft plans for this week
  const weekDraftPlans = useMemo(
    () =>
      (plans ?? []).filter(
        (p) =>
          p.status === 'draft' &&
          weekDays.some((d) => format(d, 'yyyy-MM-dd') === p.plan_date)
      ),
    [plans, weekDays]
  );

  // Drop zone for the unassigned sidebar — dropping a scheduled job here removes it.
  const { setNodeRef: setUnassignedDropRef, isOver: isOverUnassigned } = useDroppable({
    id: 'unassigned',
    data: { unassigned: true },
  });

  // Clean undo: take a planned job off the week and back to the unassigned queue.
  // Only plans made here; builds booked in JobNimbus are changed in JobNimbus.
  const unscheduleJob = async (job: Job) => {
    try {
      await updateJob.mutateAsync({ id: job.id, update: { planned_date: null } });
      toast.success(`Took ${job.customer_name} off the plan`);
    } catch {
      toast.error('Couldn\'t take the job off the plan. Try again.');
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;

    const job = active.data.current?.job as Job | undefined;
    if (!job) return;

    // Dropped onto the unassigned sidebar → take it off the plan
    if (over.id === 'unassigned' || over.data.current?.unassigned) {
      if (job.planned_date) {
        await unscheduleJob(job);
      } else if (job.suggested_date) {
        await clearSuggestions.mutateAsync({ job_ids: [job.id] }).catch(() => toast.error("Couldn't remove the suggestion."));
      }
      return;
    }
    if (!isPlannable(job)) return;

    // Dropped onto a day column → schedule / move to that day
    const dayStr = over.data.current?.date as string | undefined;
    if (!dayStr) return;

    // A suggestion dragged to a day keeps its suggested PM and crew unless one PM is picked
    const fromSuggestion = !job.planned_date && !!job.suggested_date;
    const useSuggestedPm = fromSuggestion && selectedPMIds.length !== 1 && !!job.suggested_pm_id;
    if (!useSuggestedPm && selectedPMIds.length === 0) {
      toast.error('Select a PM from the header before scheduling jobs');
      return;
    }
    if (!useSuggestedPm && selectedPMIds.length > 1) {
      toast.error('Select exactly one PM to assign this job to');
      return;
    }

    const assignedPmId = useSuggestedPm ? job.suggested_pm_id! : selectedPMIds[0];
    const pmName = activePMs.find((p) => p.id === assignedPmId)?.name ?? '';

    // No-Build Dates: the customer asked us not to build then — make the scheduler confirm
    const sameDay = job.planned_date === dayStr;
    const clash = sameDay ? null : noBuildConflict(job, dayStr);
    if (clash) {
      const multiDay = job.duration_days > 1 ? ` (a ${job.duration_days}-day build)` : '';
      const ok = confirm(
        `${job.customer_name} asked us not to build ${describeNoBuild(clash)}.\n\n` +
        `Schedule on ${format(parseISO(dayStr), 'EEE, MMM d')}${multiDay} anyway?`,
      );
      if (!ok) return;
    }

    // Ready check: the notes say something may stop the build and nobody has cleared it
    if (!sameDay && readyBlocked(job)) {
      const what = job.ready_status === 'hold' ? 'is on hold' : 'may not be ready';
      const ok = confirm(
        `${job.customer_name} ${what}: ${readyIssue(job)}.\n\n` +
        `Plan it for ${format(parseISO(dayStr), 'EEE, MMM d')} anyway? ` +
        `It won't be sent to JobNimbus until someone marks it OK to schedule.`,
      );
      if (!ok) return;
    }

    try {
      await updateJob.mutateAsync({
        id: job.id,
        update: {
          planned_date: dayStr,
          planned_pm_id: assignedPmId,
          ...(fromSuggestion && job.suggested_crew_id ? { planned_crew_id: job.suggested_crew_id } : {}),
          ...(clash ? { override_no_build: true } : {}),
        },
      });
      toast.success(`Planned ${job.customer_name} for ${format(parseISO(dayStr), 'EEE, MMM d')} with ${pmName}`);
    } catch (err: any) {
      // 409 = No-Build Dates the page didn't know about yet (e.g. just added elsewhere)
      toast.error(
        err?.response?.status === 409
          ? `Not scheduled: ${err.response.data.detail} Refresh and try again if you still want this day.`
          : 'Failed to schedule job',
      );
    }
  };

  const handleConfirmWeek = async () => {
    let confirmed = 0;
    for (const plan of weekDraftPlans) {
      try {
        await confirmPlan.mutateAsync(plan.id);
        confirmed++;
      } catch {
        toast.error(`Failed to confirm plan ${plan.id}`);
      }
    }
    if (confirmed > 0) {
      toast.success(`Confirmed ${confirmed} plans`);
    }
  };

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      {/* Desktop: side-by-side layout | Mobile: stacked */}
      <div className="flex flex-col md:flex-row h-full">
        {/* Unassigned jobs sidebar — full sidebar on desktop, collapsible panel on mobile */}
        <div className="md:w-80 lg:w-96 md:border-r flex flex-col md:shrink-0 overflow-hidden border-b md:border-b-0">
          {/* Desktop header (always visible) */}
          <div className="hidden md:block p-4 shrink-0">
            <h3 className="text-sm font-semibold mb-1">Unassigned Jobs</h3>
            <p className="text-xs text-muted-foreground">
              {unassignedJobs.length} jobs to schedule — drag into a day, or drag a
              scheduled job back here to remove it
            </p>
          </div>
          {/* Mobile collapsible header */}
          <button
            type="button"
            className="md:hidden w-full flex items-center justify-between p-3 bg-muted/50 text-left"
            onClick={() => setUnassignedOpenMobile(o => !o)}
          >
            <div>
              <p className="text-sm font-semibold">Unassigned Jobs</p>
              <p className="text-[11px] text-muted-foreground">
                {unassignedJobs.length} jobs · tap to {unassignedOpenMobile ? 'collapse' : 'expand'}
              </p>
            </div>
            {unassignedOpenMobile ? <ChevronLeft className="h-4 w-4 rotate-90" /> : <ChevronRight className="h-4 w-4 rotate-90" />}
          </button>
          <Separator className="shrink-0 hidden md:block" />
          {(readyOpen?.length ?? 0) > 0 && (
            <div className={cn('shrink-0 border-b bg-amber-50/50 px-3 py-2.5', !unassignedOpenMobile && 'hidden md:block')}>
              <p className="text-xs font-semibold text-amber-950">
                Needs a decision ({readyOpen!.filter((j) => j.ready_status === 'flagged').length})
                {readyOpen!.some((j) => j.ready_status === 'hold') && (
                  <span className="font-normal text-muted-foreground">
                    {' '}· {readyOpen!.filter((j) => j.ready_status === 'hold').length} on hold
                  </span>
                )}
              </p>
              <p className="mb-2 text-[11px] leading-snug text-muted-foreground">
                The notes say something may stop these builds. Click one to answer.
              </p>
              <ul className="max-h-48 space-y-1.5 overflow-y-auto pr-1">
                {readyOpen!.map((job) => (
                  <li key={job.id} className="min-w-0">
                    <p className="truncate text-[11px] font-medium">
                      {job.customer_name}
                      {job.bucket === 'coming_soon' && (
                        <span className="font-normal text-muted-foreground"> · coming soon</span>
                      )}
                    </p>
                    <ReadyCheckBadge job={job} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          <ScrollArea className={`flex-1 min-h-0 ${unassignedOpenMobile ? 'max-h-[40vh]' : 'hidden md:block'}`}>
            <div
              ref={setUnassignedDropRef}
              className={cn(
                'space-y-1.5 p-3 min-h-full rounded-md transition-colors',
                isOverUnassigned && 'ring-2 ring-primary bg-primary/5',
              )}
            >
              {unassignedJobs.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-6">
                  No unassigned jobs
                </p>
              ) : (
                unassignedJobs.map((job) => (
                  <UnassignedJobRow key={job.id} job={job} />
                ))
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Main area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 p-3 md:p-4 border-b">
            <div className="flex items-center gap-2 md:gap-3">
              <Button variant="outline" size="icon" onClick={prevWeek}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="text-center flex-1 lg:flex-none">
                <p className="text-sm font-semibold">
                  Week of {format(selectedWeekStart, 'MMM d, yyyy')}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {format(selectedWeekStart, 'MMM d')} – {format(addDays(selectedWeekStart, 6), 'MMM d')}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  Gray = booked in JobNimbus · Dashed = planned here, not sent yet · Dotted = suggested, not saved
                </p>
              </div>
              <Button variant="outline" size="icon" onClick={nextWeek}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              {/* PM toggles — select one to assign jobs */}
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-[10px] text-muted-foreground mr-1">Assign to:</span>
                {activePMs.map((pm) => (
                  <Button
                    key={pm.id}
                    variant={selectedPMIds.includes(pm.id) ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => togglePM(pm.id)}
                    className="text-xs h-7"
                  >
                    {pm.name}
                  </Button>
                ))}
                {selectedPMIds.length === 0 && (
                  <span className="text-[10px] text-amber-600 ml-1">← select a PM</span>
                )}
              </div>

              <Separator orientation="vertical" className="h-6 hidden sm:block" />

              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => handleSuggest('roofs')}
                  disabled={suggestBuilds.isPending}
                  title="Pencil full roofs into the open days this week, around what's already planned or booked. Repairs and siding stay manual. Nothing is saved or sent."
                >
                  <Sparkles className="mr-1 h-3.5 w-3.5" />
                  {suggesting === 'roofs' ? 'Suggesting…' : 'Suggest roofs'}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => handleSuggest('gutters')}
                  disabled={suggestBuilds.isPending}
                  title="Pencil in gutters: gutter-only jobs, and gutters on roofs that are already done (never before the roof; after the siding only if the job says siding first). Longest wait first. Nothing is saved or sent."
                >
                  <Sparkles className="mr-1 h-3.5 w-3.5" />
                  {suggesting === 'gutters' ? 'Suggesting…' : 'Suggest gutters'}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => handleSuggest('siding')}
                  disabled={suggestBuilds.isPending}
                  title="Pencil in siding: full siding jobs, and siding on jobs whose main trade is done (after the gutters unless the job says siding first). Longest wait first. Siding repairs stay manual. Nothing is saved or sent."
                >
                  <Sparkles className="mr-1 h-3.5 w-3.5" />
                  {suggesting === 'siding' ? 'Suggesting…' : 'Suggest siding'}
                </Button>
                {weekSuggested > 0 && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs"
                      disabled={keepSuggestions.isPending}
                      onClick={async () => {
                        try {
                          const r = await keepSuggestions.mutateAsync({ week_start: weekKey });
                          toast.success(`Kept ${r.kept}. They're planned now; push them when you're ready.`);
                        } catch {
                          toast.error("Couldn't keep them. Try again.");
                        }
                      }}
                    >
                      <Check className="mr-1 h-3.5 w-3.5" />
                      Keep all ({weekSuggested})
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 text-xs text-muted-foreground"
                      disabled={clearSuggestions.isPending}
                      onClick={() => clearSuggestions.mutateAsync({ week_start: weekKey })
                        .catch(() => toast.error("Couldn't clear them. Try again."))}
                    >
                      <X className="mr-1 h-3.5 w-3.5" />
                      Clear suggestions
                    </Button>
                  </>
                )}
              </div>

              <PushToJobNimbus plannedCount={plannedCount} />

              {weekDraftPlans.length > 0 && (
                <Button
                  size="sm"
                  onClick={handleConfirmWeek}
                  disabled={confirmPlan.isPending}
                >
                  <Check className="h-4 w-4 mr-1" />
                  Confirm Week ({weekDraftPlans.length})
                </Button>
              )}
            </div>
          </div>

          {/* 7-day grid — horizontal scroll on mobile (each column 220px min) */}
          <div className="flex-1 overflow-auto p-3 md:p-4">
            <div
              className="grid gap-2 md:gap-3 h-full min-h-[500px]"
              style={{ gridTemplateColumns: 'repeat(7, minmax(220px, 1fr))' }}
            >
              {weekDays.map((day) => {
                const key = format(day, 'yyyy-MM-dd');
                return (
                  <DayColumn
                    key={key}
                    date={day}
                    jobs={daysByKey[key]?.planned ?? []}
                    booked={daysByKey[key]?.booked ?? []}
                    suggested={daysByKey[key]?.suggested ?? []}
                    pms={activePMs}
                    pmJobCounts={pmJobCountsByDay[key] ?? {}}
                    isToday={isToday(day)}
                    onUnschedule={unscheduleJob}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </DndContext>
  );
}
