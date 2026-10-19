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
      // Each job is several JobNimbus calls; give a full week's push time to finish
      const { data } = await api.post('/schedule/push', { job_ids: jobIds }, { timeout: 300000 });
      return data as { results: PushResult[]; booked: number; failed: number };
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['pushPreview'] });
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}
