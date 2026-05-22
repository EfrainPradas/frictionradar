import { apiClient } from './apiClient';

export interface CandidateProfile {
  user_id: string;
  dominant_capabilities: string[];
  solved_pain_categories: string[];
  strengths: {
    transformation: number;
    analytics: number;
    leadership: number;
    operational: number;
    modernization: number;
  };
  inferred_positioning?: string | null;
  positioning_vectors?: Record<string, number> | null;
}

export interface AlignmentResult {
  user_id: string;
  company_id: string;
  alignment_score: number;
  alignment_tier: string;
  strategic_fit: string;
  positioning_recommendation: string;
  interview_positioning: string;
  resume_emphasis: string[];
  networking_guidance: string;
  matched_pain_categories: string[];
  matched_strengths: string[];
}

export interface VipOpenRole {
  title: string;
  url?: string | null;
  functional_area?: string | null;
  location?: string | null;
}

export interface VipOpportunity {
  company_id: string;
  company_name?: string | null;
  alignment_score: number;
  opportunity_type?: string | null;
  company_pain_summary?: string | null;
  strategic_positioning?: string | null;
  why_you_fit?: string | null;
  why_they_value_you?: string | null;
  resume_emphasis?: string[];
  networking_positioning?: string | null;
  interview_positioning?: string | null;
  open_roles?: VipOpenRole[];
}

export interface CompanyPainProfile {
  company_id: string;
  dominant_pain?: string | null;
  pain_dimensions?: Record<string, number> | null;
  recommended_positioning?: string | null;
  candidate_archetype?: string | null;
  positioning_angle?: string | null;
  resume_emphasis?: string[];
  networking_angle?: string | null;
  interview_themes?: string[];
  confidence_band?: string | null;
  evidence_depth?: string | null;
  temporal_status?: string | null;
  trend_direction?: string | null;
}

export async function extractCandidateProfile(userId: string): Promise<CandidateProfile> {
  const { data } = await apiClient.post(`/intelligence/candidates/${userId}/extract`);
  return data;
}

export async function getCandidateProfile(userId: string): Promise<CandidateProfile> {
  const { data } = await apiClient.get(`/intelligence/candidates/${userId}/profile`);
  return data;
}

export async function alignCandidateToCompany(userId: string, companyId: string): Promise<AlignmentResult> {
  const { data } = await apiClient.post(`/intelligence/candidates/${userId}/align/${companyId}`);
  return data;
}

export async function alignCandidateToAll(userId: string): Promise<AlignmentResult[]> {
  const { data } = await apiClient.post(`/intelligence/candidates/${userId}/align-all`);
  return data;
}

export async function generateVipOpportunities(userId: string, topN: number = 30): Promise<VipOpportunity[]> {
  const { data } = await apiClient.post(`/intelligence/candidates/${userId}/vip-opportunities?top_n=${topN}`);
  return data.opportunities ?? data;
}

export async function getVipOpportunities(userId: string): Promise<VipOpportunity[]> {
  const { data } = await apiClient.get(`/intelligence/candidates/${userId}/vip-opportunities`);
  return data.opportunities ?? data;
}

export async function getCompanyPainProfile(companyId: string): Promise<CompanyPainProfile> {
  const { data } = await apiClient.get(`/intelligence/companies/${companyId}/pain-profile`);
  return data;
}