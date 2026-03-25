import { differenceInDays, parseISO } from 'date-fns';
import {
  MapPin, Calendar, DollarSign, Layers, Users, Hash,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MustBuildBadge } from './MustBuildBadge';
import { DurationFlag } from './DurationFlag';
import { WeatherBadge } from './WeatherBadge';
import { MATERIAL_LABELS } from '@/types';
import { cn } from '@/lib/utils';
import type { Job } from '@/types';

export function JobCard({ job, compact = false }: { job: Job; compact?: boolean }) {
  const daysInQueue = job.date_entered
    ? differenceInDays(new Date(), parseISO(job.date_entered))
    : null;

  return (
    <Card
      className={cn(
        'transition-shadow hover:shadow-md',
        job.must_build && 'ring-2 ring-red-500/50 bg-red-50/30',
        job.crew_requirement_flag && 'border-l-4 border-l-orange-500'
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
            <Badge variant="outline" className="font-mono text-xs tabular-nums">
              {job.score.toFixed(1)}
            </Badge>
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
              {job.payment_type ?? '—'}
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

        {/* Row 4: Trade info */}
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
      </CardContent>
    </Card>
  );
}
