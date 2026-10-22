import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from './client';
import type { PushPreview, PushResult, SchedulePlan } from '@/types';

export function useSchedulePlans() {
  return useQuery<SchedulePlan[]>({
    queryKey: ['schedulePlans'],
    queryFn: async () => {
      const { data } = await api.get('/schedule/plans');
      return data;
    },
  });
}

export function useConfirmPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (planId: number) => {
      const { data } = await api.post(`/schedule/confirm/${planId}`);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schedulePlans'] });
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

/** Which planned jobs Push to JobNimbus would book, and why the others won't. */
export function usePushPreview(enabled: boolean) {
  return useQuery<PushPreview>({
    queryKey: ['pushPreview'],
    queryFn: async () => {
      const { data } = await api.get('/schedule/push-preview');
      return data;
    },
    enabled,
  });
}

export function usePushToJobNimbus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (jobIds: number[]) => {
      // The page sends one job at a time: about ten JobNimbus calls plus a notes recheck
      const { data } = await api.post('/schedule/push', { job_ids: jobIds }, { timeout: 120000 });
      return data as { results: PushResult[]; booked: number; failed: number };
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['pushPreview'] });
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

/** Move a job booked in JobNimbus to a new day: off the calendar, then booked again. */
export function useMoveBooking() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { job_id: number; new_date: string; reason: string }) => {
      const { data } = await api.post('/schedule/move', body, { timeout: 120000 });
      return data as { status: string; reason?: string; work_order?: string };
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['pushPreview'] });
    },
  });
}

/** Suggest builds: pencil in the open days of a week around what's already planned or booked. */
export function useSuggestBuilds() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { week_start: string; kind: 'roofs' | 'gutters' | 'siding'; pm_ids?: number[] }) => {
      const { data } = await api.post('/schedule/suggest', body, { timeout: 120000 });
      return data as { suggested: { job_id: number }[]; waiting?: number; reason?: string };
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  });
}

/** Keep suggestions (they become normal plans) by job, or every one in a week. */
export function useKeepSuggestions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { job_ids?: number[]; week_start?: string }) => {
      const { data } = await api.post('/schedule/suggestions/keep', body);
      return data as { kept: number };
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['pushPreview'] });
    },
  });
}

/** Dismiss suggestions by job, or every one in a week. */
export function useClearSuggestions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { job_ids?: number[]; week_start?: string }) => {
      const { data } = await api.post('/schedule/suggestions/clear', body);
      return data as { cleared: number };
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  });
}
