import { cn } from '@/lib/utils';
import type { Job } from '@/types';

/** Customer name with the JobNimbus job number beside it; the number never gets cut off. */
export function JobName({ job, className }: { job: Job; className?: string }) {
  return (
    <span className="flex min-w-0 items-baseline gap-1">
      <span className={cn('truncate', className)}>{job.customer_name}</span>
      {job.follow_up_trade && (
        <span className="shrink-0 rounded bg-sky-100 px-1 text-[9px] font-medium capitalize text-sky-800">
          {job.follow_up_trade}
        </span>
      )}
      {job.jn_number && (
        <span className="shrink-0 text-xs font-normal tabular-nums text-muted-foreground">{job.jn_number}</span>
      )}
    </span>
  );
}
