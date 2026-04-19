import axios from 'axios';
import { apiClient } from './apiClient';
import type { OpportunityHypothesis } from '../types/hypothesis';

export const hypothesisService = {
  trigger: (companyId: string): Promise<OpportunityHypothesis> =>
    apiClient
      .post<OpportunityHypothesis>(`/companies/${companyId}/hypothesis`)
      .then((r) => r.data),

  list: (companyId: string): Promise<OpportunityHypothesis[]> =>
    apiClient
      .get<OpportunityHypothesis[]>(`/companies/${companyId}/hypotheses`)
      .then((r) => r.data),

  latest: (companyId: string): Promise<OpportunityHypothesis | null> =>
    apiClient
      .get<OpportunityHypothesis>(`/companies/${companyId}/hypotheses/latest`)
      .then((r) => r.data)
      .catch((error) => {
        if (axios.isAxiosError(error) && error.response?.status === 404) {
          return null;
        }
        throw error;
      }),
};
