import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 300000,
});

export const analysisService = {
  analyzeCompany: async (payload: {
    domain: string;
    name?: string;
    industry?: string;
  }) => {
    const response = await apiClient.post('/analyze-company', payload);
    return response.data;
  },
  
  recalculateAll: async (companyId: string) => {
    const response = await apiClient.post(`/companies/${companyId}/recalculate-all`);
    return response.data;
  },
  
  getCompanyType: async (companyId: string) => {
    const response = await apiClient.get(`/companies/${companyId}/type`);
    return response.data;
  },
  
  getCompanyVerdict: async (companyId: string) => {
    const response = await apiClient.get(`/companies/${companyId}/verdict`);
    return response.data;
  },

  getHiringIntelligence: async (companyId: string) => {
    const response = await apiClient.get(`/companies/${companyId}/hiring-intelligence`);
    return response.data;
  },

  getCompanyEvaluation: async (companyId: string): Promise<CompanyEvaluation> => {
    const response = await apiClient.get(`/companies/${companyId}/evaluation`);
    return response.data;
  },
};

export type KpiLevel = 'low' | 'moderate' | 'high';
export type DiagnosticState =
  | 'insufficient_evidence'
  | 'broad_hiring_pattern_detected'
  | 'specific_pain_emerging'
  | 'specific_pain_identified'
  | 'ready_for_positioning';

export interface CompanyEvaluation {
  kpis: {
    extraction_coverage: KpiLevel;
    hiring_pressure: KpiLevel;
    function_concentration: KpiLevel;
    pain_clarity: KpiLevel;
    company_type_confidence: KpiLevel;
    positioning_readiness: KpiLevel;
  };
  diagnostic_state: DiagnosticState;
  summary: string;
  next_best_step: string;
  allow_specific_pain_output: boolean;
  evidence: {
    open_positions_count: number;
    visible_hiring_areas: number;
    visible_job_cards: number;
    parsed_titles: number;
    parsed_descriptions: number;
    distinct_signal_types: number;
  };
}

export default apiClient;