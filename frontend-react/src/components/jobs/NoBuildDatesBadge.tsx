import { CalendarX } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { describeNoBuild, formatNoBuildRange } from '@/lib/no-build';
import type { NoBuildWindow } from '@/types';

/** "No build Oct 20–27" chip; the tooltip lists every window with its reason. */
export function NoBuildDatesBadge({
  windows,
  small = false,
}: {
  windows: NoBuildWindow[] | null | undefined;
  small?: boolean;
}) {
  if (!windows || windows.length === 0) return null;
  const [first, ...rest] = windows;

  return (
    <Tooltip>
      <TooltipTrigger render={<span />}>
        <Badge
          variant="outline"
          className={cn(
            'gap-1 bg-violet-100 text-violet-800 border-violet-300 cursor-help',
            small ? 'text-[9px] px-1 py-0 gap-0.5' : 'text-[10px]',
          )}
        >
          <CalendarX className={small ? 'h-2.5 w-2.5' : 'h-3 w-3'} />
          No build {formatNoBuildRange(first)}
          {rest.length > 0 && ` +${rest.length}`}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <div className="text-xs space-y-1">
          <p className="font-medium">No-Build Dates</p>
          {windows.map((w) => (
            <p key={`${w.start}-${w.end}`}>{describeNoBuild(w)}</p>
          ))}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
