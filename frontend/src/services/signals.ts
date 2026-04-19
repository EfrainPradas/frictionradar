import { apiClient } from './apiClient';
import type { CompanySignal } from '../types/signal';

export const signalsService = {
  list: (companyId: string): Promise<CompanySignal[]> =>
    apiClient
      .get<CompanySignal[]>(`/companies/${companyId}/signals`)
      .then((r) => r.data),
};
