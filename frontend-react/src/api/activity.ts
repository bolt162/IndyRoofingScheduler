import { useInfiniteQuery } from '@tanstack/react-query';
import api from './client';

export interface ActivityRow {
  id: number;
  at: string;
  kind: 'user' | 'job' | 'email' | 'note' | 'error' | 'api';
  source: string;
  action: string;
  status: 'ok' | 'error' | 'skipped';
  actor: string | null;
  job_id: number | null;
  duration_ms: number | null;
  detail: string | null;
}

export interface ActivityFilters {
  kind?: string;
  status?: string;
  q?: string;
}

export function useActivity(filters: ActivityFilters) {
  return useInfiniteQuery({
    queryKey: ['activity', filters],
    initialPageParam: undefined as number | undefined,
    queryFn: async ({ pageParam }) => {
      const params: Record<string, string | number> = { limit: 100 };
      if (filters.kind) params.kind = filters.kind;
      if (filters.status) params.status = filters.status;
      if (filters.q) params.q = filters.q;
      if (pageParam) params.before_id = pageParam;
      const { data } = await api.get<{ rows: ActivityRow[]; more: boolean }>('/admin/activity', { params });
      return data;
    },
    getNextPageParam: (last) => (last.more && last.rows.length ? last.rows[last.rows.length - 1].id : undefined),
    refetchInterval: 30_000,
  });
}
