import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from './client';

// Check weather for a single job
export function useCheckWeather() {
  return useMutation({
    mutationFn: async ({ jobId, targetDate }: { jobId: number; targetDate?: string }) => {
      const params = targetDate ? { target_date: targetDate } : {};
      const { data } = await api.get(`/weather/check/${jobId}`, { params });
      return data;
    },
  });
}

// Check weather for all scheduled jobs — returns rollback + decision info
export function useCheckAllWeather() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/weather/check-all-scheduled');
      return data as {
        results: any[];
        rolled_back: { job_id: number; customer_name: string; detail: string }[];
        scheduler_decision: { job_id: number; customer_name: string; detail: string; forecast: any }[];
        total_checked: number;
      };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}

// Scheduler Decision — include or exclude a marginal weather job
export function useWeatherDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ jobId, action }: { jobId: number; action: 'include' | 'exclude' }) => {
      const { data } = await api.post(`/weather/${jobId}/decision`, { action });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['bucketCounts'] });
    },
  });
}

// Force BamWx/Clarity Wx check on a specific job
export function useForceBamwxCheck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ jobId, targetDate }: { jobId: number; targetDate?: string }) => {
      const params = targetDate ? { target_date: targetDate } : {};
      const { data } = await api.post(`/weather/${jobId}/bamwx-check`, null, { params });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

// Check weather provider status (which API is active)
export function useWeatherProviderStatus() {
  return useQuery({
    queryKey: ['weatherProvider'],
    queryFn: async () => {
      const { data } = await api.get('/weather/provider-status');
      return data as {
        provider: 'claritywx' | 'openmeteo';
        connected: boolean;
        usage: { monthlyLimit: number; requestCount: number; requestsRemaining: number } | null;
      };
    },
    staleTime: 60000, // Cache for 1 minute
  });
}
