import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from './client';
import type { Job, JobCreate, JobUpdate, JobNote, NotBuiltRequest, BucketCounts, JobBucket } from '@/types';

// List jobs, optionally filtered by bucket
export function useJobs(bucket?: JobBucket) {
  return useQuery<Job[]>({
    queryKey: ['jobs', bucket],
    queryFn: async () => {
      const params = bucket ? { bucket } : {};
      const { data } = await api.get('/jobs/', { params });
      return data;
    },
  });
}

// Get single job
export function useJob(id: number) {
  return useQuery<Job>({
    queryKey: ['job', id],
    queryFn: async () => {
      const { data } = await api.get(`/jobs/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

// Bucket counts
export function useBucketCounts() {
  return useQuery<BucketCounts>({
    queryKey: ['bucketCounts'],
    queryFn: async () => {
      const { data } = await api.get('/jobs/buckets');
      return data;
    },
    refetchInterval: 30000, // Auto-refresh every 30s
  });
}

// Update job
export function useUpdateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, update }: { id: number; update: JobUpdate }) => {
      const { data } = await api.patch(`/jobs/${id}`, update);
      return data as Job;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}

// Set must-build
export function useSetMustBuild() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, deadline, reason }: { id: number; deadline: string; reason?: string }) => {
      const { data } = await api.post(`/jobs/${id}/must-build`, {
        must_build_deadline: deadline,
        must_build_reason: reason,
      });
      return data as Job;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}

// Background sync status — polls to check if initial sync is still running
export function useSyncStatus() {
  return useQuery<{ running: boolean; last_result: any; error: string | null }>({
    queryKey: ['syncStatus'],
    queryFn: async () => {
      const { data } = await api.get('/sync-status');
      return data;
    },
    refetchInterval: (query) => {
      // Poll every 2s while running, stop when done
      return query.state.data?.running ? 2000 : false;
    },
  });
}

// Sync jobs from JobNimbus
export function useSyncJN() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/jobs/sync');
      return data as { created: number; updated: number; scanned?: number; errors: any[]; total_from_jn: number };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}

// Create a new job manually
export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: JobCreate) => {
      const { data: resp } = await api.post('/jobs/', data);
      return resp as Job;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}

// Mark not built
export function useMarkNotBuilt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, request }: { id: number; request: NotBuiltRequest }) => {
      const { data } = await api.post(`/jobs/${id}/not-built`, request);
      return data as Job;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}

// Set standalone option (Saturday Build or Sales Rep Managed)
export function useSetStandaloneOption() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, option }: { id: number; option: 'saturday_build' | 'sales_rep_managed' }) => {
      const { data } = await api.post(`/jobs/${id}/standalone-option`, { option });
      return data as Job;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

// Get all system-generated notes for a job
export function useJobNotes(jobId: number, enabled = true) {
  return useQuery<JobNote[]>({
    queryKey: ['jobNotes', jobId],
    queryFn: async () => {
      const { data } = await api.get(`/jobs/${jobId}/notes`);
      return data;
    },
    enabled: enabled && !!jobId,
  });
}

// Push a single note to JobNimbus (manual trigger)
export function usePushNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (noteId: number) => {
      const { data } = await api.post(`/jobs/notes/${noteId}/push`);
      return data as {
        status: 'pushed' | 'already_pushed';
        note_id: number;
        pushed_at: string;
        jn_note_id: string;
      };
    },
    onSuccess: (_data, noteId) => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['jobNotes'] });
      qc.invalidateQueries({ queryKey: ['job'] });
    },
  });
}

// Mark primary trade complete (roofing done, secondary trades tracking starts)
export function useMarkPrimaryComplete() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: number) => {
      const { data } = await api.post(`/jobs/${jobId}/mark-primary-complete`);
      return data as Job;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}

// Update status of a single secondary trade on a job
export function useUpdateSecondaryTradeStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ jobId, trade, status }: {
      jobId: number;
      trade: string;
      status: 'pending' | 'in_progress' | 'complete' | 'blocked';
    }) => {
      const { data } = await api.post(`/jobs/${jobId}/secondary-trade-status`, { trade, status });
      return data as Job;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}
