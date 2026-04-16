import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from './client';
import type { SettingsMap, PM, Crew } from '@/types';

// Settings
export function useSettings() {
  return useQuery<SettingsMap>({
    queryKey: ['settings'],
    queryFn: async () => {
      const { data } = await api.get('/settings/');
      return data;
    },
  });
}

export function useUpdateSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, value }: { key: string; value: string }) => {
      const { data } = await api.put(`/settings/${key}`, { value });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] });
    },
  });
}

// PMs
export function usePMs() {
  return useQuery<PM[]>({
    queryKey: ['pms'],
    queryFn: async () => {
      const { data } = await api.get('/settings/pms');
      return data;
    },
  });
}

export function useAddPM() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, baseline, maxCap }: { name: string; baseline?: number; maxCap?: number }) => {
      const params = new URLSearchParams({ name });
      if (baseline) params.set('baseline', String(baseline));
      if (maxCap) params.set('max_cap', String(maxCap));
      const { data } = await api.post(`/settings/pms?${params.toString()}`);
      return data as PM;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pms'] });
    },
  });
}

// Update PM (edit name/capacity, activate/deactivate)
export function useUpdatePM() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, update }: {
      id: number;
      update: { name?: string; baseline_capacity?: number; max_capacity?: number; is_active?: boolean };
    }) => {
      const { data } = await api.patch(`/settings/pms/${id}`, update);
      return data as PM;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pms'] });
    },
  });
}

// Delete PM (blocked if any jobs are assigned)
export function useDeletePM() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await api.delete(`/settings/pms/${id}`);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pms'] });
    },
  });
}

// Crews
export function useCrews() {
  return useQuery<Crew[]>({
    queryKey: ['crews'],
    queryFn: async () => {
      const { data } = await api.get('/settings/crews');
      return data;
    },
  });
}

export function useAddCrew() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, specialties, rank, notes }: {
      name: string;
      specialties?: string[];
      rank?: number;
      notes?: string | null;
    }) => {
      const { data } = await api.post('/settings/crews', {
        name,
        specialties: specialties || [],
        rank: rank ?? 999,
        notes: notes ?? null,
      });
      return data as Crew;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['crews'] });
    },
  });
}

// Update crew
export function useUpdateCrew() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, update }: {
      id: number;
      update: {
        name?: string;
        specialties?: string[];
        is_active?: boolean;
        rank?: number;
        notes?: string | null;
      };
    }) => {
      const { data } = await api.patch(`/settings/crews/${id}`, update);
      return data as Crew;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['crews'] });
    },
  });
}

// Delete crew
export function useDeleteCrew() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await api.delete(`/settings/crews/${id}`);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['crews'] });
    },
  });
}

// Reset entire database
export function useResetDB() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/settings/reset-db');
      return data;
    },
    onSuccess: () => {
      // Invalidate everything
      qc.invalidateQueries();
    },
  });
}
