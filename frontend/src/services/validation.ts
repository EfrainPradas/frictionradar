import { apiClient } from './apiClient';

export interface ValidationDetail {
  name: string;
  status: 'passed' | 'failed' | 'error';
  error?: string;
}

export interface ValidationReport {
  passed: number;
  failed: number;
  errors: number;
  total: number;
  success: boolean;
  details: ValidationDetail[];
}

export interface ValidationState {
  status: 'idle' | 'running' | 'success' | 'failed';
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number;
  report: ValidationReport | null;
}

export const validationService = {
  trigger: () => apiClient.post<ValidationState>('/validation/run').then(r => r.data),
  getStatus: () => apiClient.get<ValidationState>('/validation/status').then(r => r.data),
};
