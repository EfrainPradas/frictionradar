import { create } from 'zustand';

export type HeatmapMode = 'intensity' | 'velocity' | 'opportunity';
export type RadarDimension = 'reporting' | 'process' | 'tooling' | 'scaling' | 'cx';

interface UIState {
  heatmapMode: HeatmapMode;
  setHeatmapMode: (mode: HeatmapMode) => void;

  selectedDimension: RadarDimension | null;
  setSelectedDimension: (dim: RadarDimension | null) => void;

  briefModalOpen: boolean;
  briefScope: { kind: 'market' | 'dimension' | 'company'; target: string } | null;
  openBrief: (scope: { kind: 'market' | 'dimension' | 'company'; target: string }) => void;
  closeBrief: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  heatmapMode: 'intensity',
  setHeatmapMode: (heatmapMode) => set({ heatmapMode }),

  selectedDimension: null,
  setSelectedDimension: (selectedDimension) => set({ selectedDimension }),

  briefModalOpen: false,
  briefScope: null,
  openBrief: (briefScope) => set({ briefModalOpen: true, briefScope }),
  closeBrief: () => set({ briefModalOpen: false, briefScope: null }),
}));
