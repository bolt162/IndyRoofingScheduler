import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { DurationTier } from '@/types';

const tierConfig: Record<string, { label: string; className: string }> = {
  tier_1: { label: 'Tier 1', className: 'bg-green-100 text-green-800' },
  tier_2: { label: 'Tier 2', className: 'bg-yellow-100 text-yellow-800' },
  tier_3: { label: 'Tier 3', className: 'bg-red-100 text-red-800' },
  low_slope: { label: 'Low Slope', className: 'bg-red-200 text-red-900 font-bold' },
};

export function DurationFlag({
  tier,
  days,
  confirmed,
}: {
  tier: DurationTier | null;
  days: number;
  confirmed: boolean;
}) {
  const cfg = tier ? tierConfig[tier] : null;

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-muted-foreground">
        {days}d{' '}
        {confirmed ? (
          <span className="text-green-600">✓</span>
        ) : (
          <span className="text-yellow-600">?</span>
        )}
      </span>
      {cfg && (
        <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0', cfg.className)}>
          {cfg.label}
        </Badge>
      )}
    </div>
  );
}
