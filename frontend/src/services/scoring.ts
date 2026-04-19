import axios from 'axios';
import { apiClient } from './apiClient';
import type { FrictionScore } from '../types/scoring';

export const scoringService = {
  trigger: (companyId: string): Promise<FrictionScore> =>
    apiClient
      .post<FrictionScore>(`/companies/${companyId}/score`)
      .then((r) => r.data),

  list: (companyId: string): Promise<FrictionScore[]> =>
    apiClient
      .get<FrictionScore[]>(`/companies/${companyId}/scores`)
      .then((r) => r.data),

  latest: (companyId: string): Promise<FrictionScore | null> =>
    apiClient
      .get<FrictionScore>(`/companies/${companyId}/scores/latest`)
      .then((r) => r.data)
      .catch((error) => {
        if (axios.isAxiosError(error) && error.response?.status === 404) {
          return null;
        }
        throw error;
      }),
};
