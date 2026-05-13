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
// Defensive coercion: production DB had crews.trades stored as a JSON-encoded
// string (legacy TEXT column type) rather than a real array. The backend migration
// now fixes the column type, but old responses cached by the browser may still
// have strings. This guard converts them to arrays so the UI doesn't crash.
function normalizeStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((v) => typeof v === 'string');
  if (typeof value === 'string') {
    if (!value.trim()) return [];
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.filter((v) => typeof v === 'string');
    } catch { /* fall through */ }
  }
  return [];
}

export function useCrews() {
  return useQuery<Crew[]>({
    queryKey: ['crews'],
    queryFn: async () => {
      const { data } = await api.get('/settings/crews');
      // Normalize trades + specialties — defensive against stringified arrays
      return (Array.isArray(data) ? data : []).map((c: any) => ({
        ...c,
        trades: normalizeStringArray(c?.trades),
        specialties: normalizeStringArray(c?.specialties),
      })) as Crew[];
    },
  });
}

export function useAddCrew() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, trades, specialties, rank, notes }: {
      name: string;
      trades?: string[];
      specialties?: string[];
      rank?: number;
      notes?: string | null;
    }) => {
      const { data } = await api.post('/settings/crews', {
        name,
        trades: trades || ['roofing'],
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
        trades?: string[];
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
