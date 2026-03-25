import { create } from 'zustand';
import { startOfWeek, addDays } from 'date-fns';
import type { JobBucket } from '@/types';

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
}

export const useUIStore = create<UIState>((set) => ({
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
}));
