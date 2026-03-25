import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from './client';
import type { SchedulePlan } from '@/types';

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
