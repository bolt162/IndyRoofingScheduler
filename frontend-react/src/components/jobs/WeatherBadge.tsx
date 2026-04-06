import { useState } from 'react';
import { Cloud, Sun, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { useWeatherDecision } from '@/api/weather';
import type { WeatherStatus } from '@/types';
import { cn } from '@/lib/utils';

const config: Record<string, { icon: typeof Sun; label: string; variant: 'default' | 'destructive' | 'secondary' | 'outline' }> = {
  clear: { icon: Sun, label: 'Clear', variant: 'default' },
  do_not_build: { icon: Cloud, label: 'Do Not Build', variant: 'destructive' },
  scheduler_decision: { icon: AlertTriangle, label: 'Decision Needed', variant: 'secondary' },
};

export function WeatherBadge({
  status, detail, jobId, customerName,
}: {
  status: WeatherStatus | null;
  detail?: string | null;
  jobId?: number;
  customerName?: string;
}) {
  if (!status) return null;

  const c = config[status] ?? config.clear;
  const Icon = c.icon;
  const [decisionOpen, setDecisionOpen] = useState(false);
  const weatherDecision = useWeatherDecision();

  const handleDecision = (action: 'include' | 'exclude') => {
    if (!jobId) return;
    weatherDecision.mutate(
      { jobId, action },
      { onSuccess: () => setDecisionOpen(false) },
    );
  };

  return (
    <>
      <Tooltip>
        <TooltipTrigger render={<span />}>
          <Badge
            variant={c.variant}
            className={cn(
              'gap-1 text-[10px]',
              status === 'clear' && 'bg-green-100 text-green-800 hover:bg-green-200',
              status === 'scheduler_decision' && 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200 cursor-pointer',
            )}
            onClick={status === 'scheduler_decision' && jobId ? (e) => {
              e.stopPropagation();
              setDecisionOpen(true);
            } : undefined}
          >
            <Icon className="h-3 w-3" />
            {c.label}
          </Badge>
        </TooltipTrigger>
        {detail && (
          <TooltipContent side="top" className="max-w-xs">
            <p className="text-xs">{detail}</p>
            {status === 'scheduler_decision' && <p className="text-xs font-semibold mt-1">Click to decide</p>}
          </TooltipContent>
        )}
      </Tooltip>

      {/* Scheduler Decision Dialog (spec §6.3 line 265) */}
      <Dialog open={decisionOpen} onOpenChange={setDecisionOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Weather Decision Required</DialogTitle>
            <DialogDescription>
              Marginal weather conditions for {customerName || 'this job'}. Review the forecast
              and decide whether to include or exclude from the schedule.
            </DialogDescription>
          </DialogHeader>

          <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3 text-sm">
            <p className="font-medium text-yellow-800 mb-1">Forecast Detail</p>
            <p className="text-yellow-700 text-xs">{detail || 'No detail available'}</p>
          </div>

          <DialogFooter className="flex gap-2">
            <Button
              variant="destructive"
              size="sm"
              onClick={() => handleDecision('exclude')}
              disabled={weatherDecision.isPending}
            >
              Exclude (Not Built)
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => handleDecision('include')}
              disabled={weatherDecision.isPending}
            >
              Include (Override)
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
