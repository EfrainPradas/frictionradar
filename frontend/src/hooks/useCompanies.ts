import { useQuery } from '@tanstack/react-query';
import { companiesService } from '../services/companies';
import { scoringService } from '../services/scoring';
import type { Company } from '../types/company';
import type { FrictionScore } from '../types/scoring';

// Fetch all companies
export function useCompanies() {
  return useQuery<Company[], Error>({
    queryKey: ['companies'],
    queryFn: () => companiesService.list(),
  });
}

// Fetch the latest score for a company with 404 gracefully handled as null
export function useLatestScore(companyId: string) {
  return useQuery<FrictionScore | null, Error>({
    queryKey: ['score-latest', companyId],
    queryFn: async () => {
      try {
        return await scoringService.latest(companyId);
      } catch (e: unknown) {
        if (e instanceof Error && e.message.includes('No friction score')) return null;
        throw e;
      }
    },
    enabled: !!companyId,
  });
}
