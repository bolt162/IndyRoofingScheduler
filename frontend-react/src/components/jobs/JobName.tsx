import { cn } from '@/lib/utils';
import type { Job } from '@/types';

/** Customer name with the JobNimbus job number beside it; the number never gets cut off. */
export function JobName({ job, className }: { job: Job; className?: string }) {
  return (
    <span className="flex min-w-0 items-baseline gap-1">
      <span className={cn('truncate', className)}>{job.customer_name}</span>
      {job.jn_number && (
        <span className="shrink-0 text-[10px] font-normal tabular-nums text-muted-foreground">#{job.jn_number}</span>
      )}
    </span>
  );
}
