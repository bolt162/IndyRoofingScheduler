import { useDroppable } from '@dnd-kit/core';
import { format } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { PMCapacityBar } from './PMCapacityBar';
import { WeatherOverlay } from './WeatherOverlay';
import { DraggableJobCard } from './DraggableJobCard';
import { cn } from '@/lib/utils';
import type { Job, PM } from '@/types';

interface DayColumnProps {
  date: Date;
  jobs: Job[];
  pms: PM[];
  pmJobCounts: Record<number, number>;
  isToday?: boolean;
}

export function DayColumn({ date, jobs, pms, pmJobCounts, isToday }: DayColumnProps) {
  const dateStr = format(date, 'yyyy-MM-dd');
  const { setNodeRef, isOver } = useDroppable({
    id: `day-${dateStr}`,
    data: { date: dateStr },
  });

  const dayName = format(date, 'EEE');
  const dayDate = format(date, 'MMM d');

  return (
    <Card
      ref={setNodeRef}
      className={cn(
        'flex flex-col overflow-hidden transition-colors',
        isOver && 'ring-2 ring-primary bg-primary/5',
        isToday && 'border-primary'
      )}
    >
      <CardHeader className="p-3 pb-1">
        <CardTitle className="text-sm flex items-center justify-between">
          <span className={cn(isToday && 'text-primary font-bold')}>
            {dayName}
          </span>
          <span className="text-xs text-muted-foreground font-normal">{dayDate}</span>
        </CardTitle>
      </CardHeader>

      <CardContent className="p-3 pt-0 flex-1 flex flex-col gap-2">
        {/* PM Capacity bars */}
        {pms.length > 0 && (
          <div className="space-y-1.5">
            {pms.map((pm) => (
              <PMCapacityBar
                key={pm.id}
                pmName={pm.name}
                current={pmJobCounts[pm.id] ?? 0}
                baseline={pm.baseline_capacity}
                max={pm.max_capacity}
              />
            ))}
            <Separator className="my-1" />
          </div>
        )}

        {/* Job cards */}
        <ScrollArea className="flex-1 min-h-[100px]">
          <div className="space-y-2">
            {jobs.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">
                Drop jobs here
              </p>
            ) : (
              jobs.map((job) => (
                <DraggableJobCard key={job.id} job={job} />
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
