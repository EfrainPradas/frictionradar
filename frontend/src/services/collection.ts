import { apiClient } from './apiClient';
import type { CollectionRun } from '../types/collection';

export const collectionService = {
  trigger: (companyId: string): Promise<{ message: string; run_id: string }> =>
    apiClient
      .post(`/companies/${companyId}/collect`)
      .then((r) => r.data),

  listRuns: (companyId: string): Promise<CollectionRun[]> =>
    apiClient
      .get<CollectionRun[]>(`/companies/${companyId}/collection-runs`)
      .then((r) => r.data),
};
