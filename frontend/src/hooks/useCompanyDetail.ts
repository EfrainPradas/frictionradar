import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { companiesService } from '../services/companies';
import { signalsService } from '../services/signals';
import { collectionService } from '../services/collection';
import { scoringService } from '../services/scoring';
import { hypothesisService } from '../services/hypothesis';
import { analysisService } from '../services/analysis';
import type { FrictionScore } from '../types/scoring';
import type { OpportunityHypothesis } from '../types/hypothesis';

export function useCompanyDetail(companyId: string) {
  const qc = useQueryClient();

  const company = useQuery({
    queryKey: ['company', companyId],
    queryFn: () => companiesService.get(companyId),
    enabled: !!companyId,
  });

  const signals = useQuery({
    queryKey: ['signals', companyId],
    queryFn: () => signalsService.list(companyId),
    enabled: !!companyId,
  });

  const collectionRuns = useQuery({
    queryKey: ['collection-runs', companyId],
    queryFn: () => collectionService.listRuns(companyId),
    enabled: !!companyId,
  });

  const latestScore = useQuery<FrictionScore | null, Error>({
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

  const latestHypothesis = useQuery<OpportunityHypothesis | null, Error>({
    queryKey: ['hypothesis-latest', companyId],
    queryFn: async () => {
      try {
        return await hypothesisService.latest(companyId);
      } catch (e: unknown) {
        if (e instanceof Error && e.message.includes('No hypothesis')) return null;
        throw e;
      }
    },
    enabled: !!companyId,
  });

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['company', companyId] });
    qc.invalidateQueries({ queryKey: ['signals', companyId] });
    qc.invalidateQueries({ queryKey: ['collection-runs', companyId] });
    qc.invalidateQueries({ queryKey: ['score-latest', companyId] });
    qc.invalidateQueries({ queryKey: ['hypothesis-latest', companyId] });
    qc.invalidateQueries({ queryKey: ['companies'] });
    qc.invalidateQueries({ queryKey: ['company-type', companyId] });
    qc.invalidateQueries({ queryKey: ['company-verdict', companyId] });
  };

  const runCollection = useMutation({
    mutationFn: () => collectionService.trigger(companyId),
    onSuccess: invalidateAll,
  });

  const recomputeScore = useMutation({
    mutationFn: () => scoringService.trigger(companyId),
    onSuccess: invalidateAll,
  });

  const generateHypothesis = useMutation({
    mutationFn: () => hypothesisService.trigger(companyId),
    onSuccess: invalidateAll,
  });

  const recalculateAll = useMutation({
    mutationFn: () => analysisService.recalculateAll(companyId),
    onSuccess: invalidateAll,
  });

  return {
    company,
    signals,
    collectionRuns,
    latestScore,
    latestHypothesis,
    runCollection,
    recomputeScore,
    generateHypothesis,
    recalculateAll,
  };
}
