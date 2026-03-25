import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

export function PMCapacityBar({
  current,
  baseline,
  max,
  pmName,
}: {
  current: number;
  baseline: number;
  max: number;
  pmName: string;
}) {
  const pct = max > 0 ? (current / max) * 100 : 0;
  const overBaseline = current > baseline;
  const atMax = current >= max;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium truncate">{pmName}</span>
        <span
          className={cn(
            'tabular-nums',
            atMax && 'text-red-600 font-bold',
            overBaseline && !atMax && 'text-yellow-600'
          )}
        >
          {current}/{max}
        </span>
      </div>
      <Progress
        value={pct}
        className={cn(
          'h-2',
          atMax && '[&>div]:bg-red-500',
          overBaseline && !atMax && '[&>div]:bg-yellow-500'
        )}
      />
    </div>
  );
}
