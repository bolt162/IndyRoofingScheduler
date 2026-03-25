import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from './client';

export function useCheckWeather() {
  return useMutation({
    mutationFn: async ({ jobId, targetDate }: { jobId: number; targetDate?: string }) => {
      const params = targetDate ? { target_date: targetDate } : {};
      const { data } = await api.get(`/weather/check/${jobId}`, { params });
      return data;
    },
  });
}

export function useCheckAllWeather() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/weather/check-all-scheduled');
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}
