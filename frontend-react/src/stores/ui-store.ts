import { create } from 'zustand';
import { startOfWeek, addDays } from 'date-fns';
import type { JobBucket, ScoringResponse } from '@/types';

interface UIState {
  // Week selector
  selectedWeekStart: Date;
  setSelectedWeekStart: (date: Date) => void;
  nextWeek: () => void;
  prevWeek: () => void;

  // PM selection for weekly plan
  selectedPMIds: number[];
  setSelectedPMIds: (ids: number[]) => void;
  togglePM: (id: number) => void;

  // Job list filter
  activeBucket: JobBucket | 'all';
  setActiveBucket: (bucket: JobBucket | 'all') => void;

  // Map mode
  mapMode: 'cluster' | 'pm';
  setMapMode: (mode: 'cluster' | 'pm') => void;

  // Sidebar
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  // Scoring results — persists across navigation, cleared on page refresh
  latestScoringResult: ScoringResponse | null;
  setLatestScoringResult: (result: ScoringResponse | null) => void;

  // Helper: look up recommended PM for a job from latest scoring result
  getPMForJob: (jobId: number) => { pmId: number; pmName: string } | null;
}

export const useUIStore = create<UIState>((set, get) => ({
  // Default to current week's Monday
  selectedWeekStart: startOfWeek(new Date(), { weekStartsOn: 1 }),
  setSelectedWeekStart: (date) => set({ selectedWeekStart: date }),
  nextWeek: () => set((s) => ({ selectedWeekStart: addDays(s.selectedWeekStart, 7) })),
  prevWeek: () => set((s) => ({ selectedWeekStart: addDays(s.selectedWeekStart, -7) })),

  selectedPMIds: [],
  setSelectedPMIds: (ids) => set({ selectedPMIds: ids }),
  togglePM: (id) =>
    set((s) => ({
      selectedPMIds: s.selectedPMIds.includes(id)
        ? s.selectedPMIds.filter((i) => i !== id)
        : [...s.selectedPMIds, id],
    })),

  activeBucket: 'to_schedule',
  setActiveBucket: (bucket) => set({ activeBucket: bucket }),

  mapMode: 'cluster',
  setMapMode: (mode) => set({ mapMode: mode }),

  sidebarOpen: true,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  // Scoring results
  latestScoringResult: null,
  setLatestScoringResult: (result) => set({ latestScoringResult: result }),

  getPMForJob: (jobId: number) => {
    const result = get().latestScoringResult;
    if (!result?.pm_plan) return null;
    for (const pm of result.pm_plan) {
      for (const job of pm.jobs) {
        if (job.job_id === jobId) {
          return { pmId: pm.pm_id, pmName: pm.pm_name };
        }
      }
    }
    return null;
  },
}));
