import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../services/temporal';

export function useTemporalDeltas(companyId: string, lookbackDays: number = 30) {
  return useQuery({
    queryKey: ['temporal-deltas', companyId, lookbackDays],
    queryFn: () => temporalService.getDeltas(companyId, lookbackDays),
    enabled: !!companyId,
  });
}

export function useTemporalVelocity(companyId: string, lookbackDays: number = 30) {
  return useQuery({
    queryKey: ['temporal-velocity', companyId, lookbackDays],
    queryFn: () => temporalService.getVelocity(companyId, lookbackDays),
    enabled: !!companyId,
  });
}

export function useTemporalDiagnostic(companyId: string, lookbackDays: number = 30) {
  return useQuery({
    queryKey: ['temporal-diagnostic', companyId, lookbackDays],
    queryFn: () => temporalService.getDiagnostic(companyId, lookbackDays),
    enabled: !!companyId,
  });
}

export function useTemporalVerdict(companyId: string, lookbackDays: number = 30) {
  return useQuery({
    queryKey: ['temporal-verdict', companyId, lookbackDays],
    queryFn: () => temporalService.getVerdict(companyId, lookbackDays),
    enabled: !!companyId,
  });
}