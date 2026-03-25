import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from './client';
import type { ScoringResponse } from '@/types';

export function useRunScoring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ pmIds, targetDate }: { pmIds?: number[]; targetDate?: string }) => {
      const params = new URLSearchParams();
      if (pmIds) pmIds.forEach((id) => params.append('pm_ids', String(id)));
      if (targetDate) params.set('target_date', targetDate);
      const { data } = await api.post(`/scoring/run?${params.toString()}`);
      return data as ScoringResponse;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useScanNotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/scoring/scan-notes');
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}
