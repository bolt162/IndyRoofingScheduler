import { Cloud, Sun, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { WeatherStatus } from '@/types';
import { cn } from '@/lib/utils';

const config: Record<string, { icon: typeof Sun; label: string; variant: 'default' | 'destructive' | 'secondary' | 'outline' }> = {
  clear: { icon: Sun, label: 'Clear', variant: 'default' },
  do_not_build: { icon: Cloud, label: 'Do Not Build', variant: 'destructive' },
  scheduler_decision: { icon: AlertTriangle, label: 'Scheduler Decision', variant: 'secondary' },
};

export function WeatherBadge({ status, detail }: { status: WeatherStatus | null; detail?: string | null }) {
  if (!status) return null;
  const c = config[status] ?? config.clear;
  const Icon = c.icon;

  return (
    <Tooltip>
      <TooltipTrigger render={<span />}>
        <Badge
          variant={c.variant}
          className={cn(
            'gap-1 text-[10px]',
            status === 'clear' && 'bg-green-100 text-green-800 hover:bg-green-200',
            status === 'scheduler_decision' && 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200'
          )}
        >
          <Icon className="h-3 w-3" />
          {c.label}
        </Badge>
      </TooltipTrigger>
      {detail && (
        <TooltipContent side="top" className="max-w-xs">
          <p className="text-xs">{detail}</p>
        </TooltipContent>
      )}
    </Tooltip>
  );
}
