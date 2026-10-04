import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from './client';

export interface EmailLogRow {
  at: string;
  job_id: number | null;
  template: string;
  recipient: string | null;
  subject: string | null;
  mode: string;
  result: string;
  detail: string | null;
}

export interface EmailStatus {
  mode: 'off' | 'test' | 'live';
  weather_slowdown_date: string | null;
  next_thursday: string;
  recent: EmailLogRow[];
}

export interface PreviewRow {
  job_id: number;
  customer: string;
  trade: string;
  rep: string;
  email: string;
  template: string | null;
  label: string;
  reason: string;
  subject: string;
  jobs_ahead: number | null;
  notes: string[];
}

export interface EmailPreview {
  for: string;
  rows: PreviewRow[];
  sending: number;
  fix: PreviewRow[];
  long_wait: { customer: string; rep: string; weeks: number }[];
  text: string;
}

export interface TeamMember {
  id: number;
  jn_name: string;
  display_name: string;
  role: 'rep' | 'pm' | 'ops' | 'owner';
  email: string | null;
  phone: string | null;
  is_active: boolean;
}

export interface ResearchedProduct {
  id: number;
  raw_text: string;
  display_name: string | null;
  manufacturer: string | null;
  impact_class: number | null;
  composition: string | null;
  status: string;
  confidence: string | null;
  summary: string | null;
  sources: string | null;
  reviewed_by: string | null;
}

export function useEmailStatus() {
  return useQuery<EmailStatus>({
    queryKey: ['emails', 'status'],
    queryFn: async () => (await api.get('/emails/status')).data,
  });
}

export function useEmailPreview() {
  return useQuery<EmailPreview>({
    queryKey: ['emails', 'preview'],
    queryFn: async () => (await api.get('/emails/preview')).data,
    staleTime: 60_000,
  });
}

export function useJobEmail(jobId: number | null) {
  return useQuery<{ template: string | null; subject?: string; html?: string; reason?: string }>({
    queryKey: ['emails', 'job', jobId],
    queryFn: async () => (await api.get(`/emails/preview/job/${jobId}`)).data,
    enabled: jobId !== null,
  });
}

function useEmailMutation<T>(fn: (arg: T) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['emails'] }),
  });
}

export const useWeatherToggle = () =>
  useEmailMutation(async (on: boolean) => (await api.post('/emails/weather-slowdown', { on })).data);

export const usePauseJob = () =>
  useEmailMutation(async ({ jobId, pause }: { jobId: number; pause: boolean }) =>
    (await api.post(`/emails/jobs/${jobId}/${pause ? 'pause' : 'resume'}`)).data);

export function useTeam() {
  return useQuery<TeamMember[]>({
    queryKey: ['emails', 'team'],
    queryFn: async () => (await api.get('/emails/team')).data,
  });
}

export const useSaveTeamMember = () =>
  useEmailMutation(async (m: Partial<TeamMember> & { id?: number }) => {
    const { id, ...body } = m;
    return (id ? await api.put(`/emails/team/${id}`, body) : await api.post('/emails/team', body)).data;
  });

export function useProducts() {
  return useQuery<ResearchedProduct[]>({
    queryKey: ['emails', 'products'],
    queryFn: async () => (await api.get('/emails/products')).data,
  });
}

export const useReviewProduct = () =>
  useEmailMutation(async (r: { id: number; approve: boolean; impact_class?: number | null; composition?: string | null; change_class?: boolean }) => {
    const { id, ...body } = r;
    return (await api.post(`/emails/products/${id}/review`, body)).data;
  });

export const useSendPreviewNow = () =>
  useEmailMutation(async () => (await api.post('/emails/run/preview')).data);
