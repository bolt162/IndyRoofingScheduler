import { useMemo } from 'react';
import { addDays, format, isSameDay, isToday, parseISO } from 'date-fns';
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { toast } from 'sonner';
import {
  ChevronLeft, ChevronRight, Calendar, AlertTriangle, Check,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { DayColumn } from '@/components/schedule/DayColumn';
import { DraggableJobCard } from '@/components/schedule/DraggableJobCard';
import { useJobs, useUpdateJob } from '@/api/jobs';
import { useSchedulePlans, useConfirmPlan } from '@/api/schedule';
import { usePMs } from '@/api/settings';
import { useUIStore } from '@/stores/ui-store';
import type { Job } from '@/types';

export function WeeklyPlanPage() {
  const { selectedWeekStart, nextWeek, prevWeek, selectedPMIds, togglePM } = useUIStore();
  const { data: allJobs } = useJobs();
  const { data: plans } = useSchedulePlans();
  const { data: pms } = usePMs();
  const updateJob = useUpdateJob();
  const confirmPlan = useConfirmPlan();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

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

  // Jobs scheduled for each day
  const jobsByDay = useMemo(() => {
    const map: Record<string, Job[]> = {};
    weekDays.forEach((d) => {
      const key = format(d, 'yyyy-MM-dd');
      map[key] = (allJobs ?? []).filter(
        (j) => j.date_scheduled && j.date_scheduled === key && j.bucket === 'scheduled'
      );
    });
    return map;
  }, [allJobs, weekDays]);

  // PM job counts per day
  const pmJobCountsByDay = useMemo(() => {
    const result: Record<string, Record<number, number>> = {};
    for (const [day, jobs] of Object.entries(jobsByDay)) {
      result[day] = {};
      for (const job of jobs) {
        if (job.assigned_pm_id) {
          result[day][job.assigned_pm_id] = (result[day][job.assigned_pm_id] ?? 0) + 1;
        }
      }
    }
    return result;
  }, [jobsByDay]);

  // Unassigned jobs (To Schedule bucket, sorted by score)
  const unassignedJobs = useMemo(
    () =>
      (allJobs ?? [])
        .filter((j) => j.bucket === 'to_schedule')
        .sort((a, b) => b.score - a.score),
    [allJobs]
  );

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

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;

    const job = active.data.current?.job as Job | undefined;
    const dayStr = over.data.current?.date as string | undefined;
    if (!job || !dayStr) return;

    // Require exactly one PM selected to assign jobs
    if (selectedPMIds.length === 0) {
      toast.error('Select a PM from the header before scheduling jobs');
      return;
    }
    if (selectedPMIds.length > 1) {
      toast.error('Select exactly one PM to assign this job to');
      return;
    }

    const assignedPmId = selectedPMIds[0];
    const pmName = activePMs.find((p) => p.id === assignedPmId)?.name ?? '';

    try {
      await updateJob.mutateAsync({
        id: job.id,
        update: {
          bucket: 'scheduled',
          date_scheduled: dayStr,
          assigned_pm_id: assignedPmId,
        },
      });
      toast.success(`Scheduled ${job.customer_name} for ${dayStr} → ${pmName}`);
    } catch {
      toast.error('Failed to schedule job');
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
      <div className="flex h-full">
        {/* Unassigned jobs sidebar — header stays fixed, job list scrolls */}
        <div className="w-72 border-r flex flex-col shrink-0 overflow-hidden">
          <div className="p-4 shrink-0">
            <h3 className="text-sm font-semibold mb-1">Unassigned Jobs</h3>
            <p className="text-xs text-muted-foreground">
              {unassignedJobs.length} jobs to schedule — drag into a day
            </p>
          </div>
          <Separator className="shrink-0" />
          <ScrollArea className="flex-1 min-h-0 p-3">
            <div className="space-y-2">
              {unassignedJobs.map((job) => (
                <DraggableJobCard key={job.id} job={job} />
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* Main area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b">
            <div className="flex items-center gap-3">
              <Button variant="outline" size="icon" onClick={prevWeek}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="text-center">
                <p className="text-sm font-semibold">
                  Week of {format(selectedWeekStart, 'MMM d, yyyy')}
                </p>
                <p className="text-xs text-muted-foreground">
                  {format(selectedWeekStart, 'MMM d')} – {format(addDays(selectedWeekStart, 6), 'MMM d')}
                </p>
              </div>
              <Button variant="outline" size="icon" onClick={nextWeek}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex items-center gap-2">
              {/* PM toggles — select one to assign jobs */}
              <div className="flex items-center gap-1">
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

              <Separator orientation="vertical" className="h-6" />

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

          {/* 7-day grid */}
          <div className="flex-1 overflow-auto p-4">
            <div className="grid gap-3 h-full min-h-[500px]" style={{ gridTemplateColumns: 'repeat(7, minmax(160px, 1fr))' }}>
              {weekDays.map((day) => {
                const key = format(day, 'yyyy-MM-dd');
                return (
                  <DayColumn
                    key={key}
                    date={day}
                    jobs={jobsByDay[key] ?? []}
                    pms={activePMs}
                    pmJobCounts={pmJobCountsByDay[key] ?? {}}
                    isToday={isToday(day)}
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
