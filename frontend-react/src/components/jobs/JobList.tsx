import { useState, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { JobCard } from './JobCard';
import { Search, ArrowUpDown } from 'lucide-react';
import type { Job } from '@/types';

type SortField = 'score' | 'date_entered' | 'customer_name' | 'rescheduled_count';

export function JobList({
  jobs,
  onJobClick,
}: {
  jobs: Job[];
  onJobClick?: (job: Job) => void;
}) {
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<SortField>('score');

  const filtered = useMemo(() => {
    let result = jobs;

    // Search
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (j) =>
          j.customer_name.toLowerCase().includes(q) ||
          j.address.toLowerCase().includes(q) ||
          j.material_type?.toLowerCase().includes(q)
      );
    }

    // Sort
    result = [...result].sort((a, b) => {
      switch (sortBy) {
        case 'score':
          return b.score - a.score;
        case 'date_entered':
          return (a.date_entered ?? '').localeCompare(b.date_entered ?? '');
        case 'customer_name':
          return a.customer_name.localeCompare(b.customer_name);
        case 'rescheduled_count':
          return b.rescheduled_count - a.rescheduled_count;
        default:
          return 0;
      }
    });

    return result;
  }, [jobs, search, sortBy]);

  return (
    <div className="flex flex-col gap-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search jobs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-9"
          />
        </div>
        <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortField)}>
          <SelectTrigger className="w-[160px] h-9">
            <ArrowUpDown className="h-3 w-3 mr-1" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="score">Score (High→Low)</SelectItem>
            <SelectItem value="date_entered">Date Entered</SelectItem>
            <SelectItem value="customer_name">Customer Name</SelectItem>
            <SelectItem value="rescheduled_count">Rescheduled Count</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Job list */}
      <ScrollArea className="flex-1">
        <div className="space-y-2 pr-2">
          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">No jobs found</p>
          ) : (
            filtered.map((job) => (
              <div
                key={job.id}
                onClick={() => onJobClick?.(job)}
                className="cursor-pointer"
              >
                <JobCard job={job} />
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
