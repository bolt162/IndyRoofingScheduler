import { addDays, format, parseISO } from 'date-fns';
import type { Job, NoBuildWindow } from '@/types';

/** Short label for a window: "Oct 20–27", "Oct 30 – Nov 2", or "Oct 20". */
export function formatNoBuildRange(w: Pick<NoBuildWindow, 'start' | 'end'>): string {
  const start = parseISO(w.start);
  const end = parseISO(w.end);
  if (w.start === w.end) return format(start, 'MMM d');
  if (format(start, 'yyyy-MM') === format(end, 'yyyy-MM')) {
    return `${format(start, 'MMM d')}–${format(end, 'd')}`;
  }
  return `${format(start, 'MMM d')} – ${format(end, 'MMM d')}`;
}

/** "Oct 20–27 (Wedding)" */
export function describeNoBuild(w: NoBuildWindow): string {
  return w.reason ? `${formatNoBuildRange(w)} (${w.reason})` : formatNoBuildRange(w);
}

/**
 * The first No-Build window a build starting on `day` (yyyy-MM-dd) would touch,
 * counting every day of a multi-day job. Mirrors backend services/no_build.py.
 */
export function noBuildConflict(
  job: Pick<Job, 'no_build_dates' | 'duration_days'>,
  day: string,
): NoBuildWindow | null {
  const last = format(addDays(parseISO(day), Math.max(job.duration_days || 1, 1) - 1), 'yyyy-MM-dd');
  return (job.no_build_dates ?? []).find((w) => w.start <= last && w.end >= day) ?? null;
}

/** The No-Build window a Must-Build deadline falls inside, if any. */
export function mustBuildDeadlineClash(
  job: Pick<Job, 'no_build_dates' | 'must_build' | 'must_build_deadline'>,
): NoBuildWindow | null {
  const deadline = job.must_build_deadline;
  if (!job.must_build || !deadline) return null;
  return (job.no_build_dates ?? []).find((w) => w.start <= deadline && w.end >= deadline) ?? null;
}
