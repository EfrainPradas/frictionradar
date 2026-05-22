import axios from 'axios';
import type {
  TemporalDeltasResponse,
  TemporalVelocityResponse,
  TemporalDiagnosticResponse,
  TemporalVerdictResponse,
  TemporalRunAnalysisResponse,
} from '../types/temporal';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const temporalClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 300000,
});

temporalClient.interceptors.response.use(
  (res) => res,
  (error) => {
    const message =
      error.response?.data?.detail || error.message || 'Unknown API error';
    return Promise.reject(new Error(message));
  }
);

export const temporalService = {
  getDeltas: async (
    companyId: string,
    lookbackDays: number = 30
  ): Promise<TemporalDeltasResponse> => {
    const response = await temporalClient.get(
      `/companies/${companyId}/temporal/deltas`,
      { params: { lookback_days: lookbackDays } }
    );
    return response.data;
  },

  getVelocity: async (
    companyId: string,
    lookbackDays: number = 30
  ): Promise<TemporalVelocityResponse> => {
    const response = await temporalClient.get(
      `/companies/${companyId}/temporal/signals/velocity`,
      { params: { lookback_days: lookbackDays } }
    );
    return response.data;
  },

  getDiagnostic: async (
    companyId: string,
    lookbackDays: number = 30
  ): Promise<TemporalDiagnosticResponse> => {
    const response = await temporalClient.get(
      `/companies/${companyId}/temporal/diagnostic`,
      { params: { lookback_days: lookbackDays } }
    );
    return response.data;
  },

  getVerdict: async (
    companyId: string,
    lookbackDays: number = 30
  ): Promise<TemporalVerdictResponse> => {
    const response = await temporalClient.get(
      `/companies/${companyId}/temporal/verdict`,
      { params: { lookback_days: lookbackDays } }
    );
    return response.data;
  },

  runAnalysis: async (
    companyId: string,
    lookbackDays: number = 30
  ): Promise<TemporalRunAnalysisResponse> => {
    const response = await temporalClient.post(
      `/companies/${companyId}/temporal/run-analysis`,
      null,
      { params: { lookback_days: lookbackDays } }
    );
    return response.data;
  },
};