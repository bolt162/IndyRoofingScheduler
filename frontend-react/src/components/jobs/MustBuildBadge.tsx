import { AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { differenceInDays, parseISO } from 'date-fns';

export function MustBuildBadge({
  deadline,
  reason,
}: {
  deadline: string | null;
  reason: string | null;
}) {
  const daysUntil = deadline ? differenceInDays(parseISO(deadline), new Date()) : null;

  return (
    <Tooltip>
      <TooltipTrigger render={<span />}>
        <Badge variant="destructive" className="gap-1 text-[10px] animate-pulse">
          <AlertTriangle className="h-3 w-3" />
          MUST BUILD
          {daysUntil !== null && ` (${daysUntil}d)`}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <div className="text-xs space-y-1">
          {deadline && <p>Deadline: {deadline}</p>}
          {reason && <p>Reason: {reason}</p>}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
