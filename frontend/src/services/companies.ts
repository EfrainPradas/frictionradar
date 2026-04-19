import { apiClient } from './apiClient';
import type { Company, CompanyCreate } from '../types/company';

async function fetchAllCompanies(): Promise<Company[]> {
  const PAGE_SIZE = 100;
  let skip = 0;
  const all: Company[] = [];

  while (true) {
    const { data } = await apiClient.get<Company[]>('/companies/', {
      params: { skip, limit: PAGE_SIZE },
    });
    all.push(...data);
    if (data.length < PAGE_SIZE) break;
    skip += PAGE_SIZE;
  }

  return all;
}

export const companiesService = {
  list: (): Promise<Company[]> => fetchAllCompanies(),

  get: (id: string): Promise<Company> =>
    apiClient.get<Company>(`/companies/${id}`).then((r) => r.data),

  create: (payload: CompanyCreate): Promise<Company> =>
    apiClient.post<Company>('/companies', payload).then((r) => r.data),

  delete: (id: string): Promise<void> =>
    apiClient.delete(`/companies/${id}`).then((r) => r.data),

  batchCreate: (
    payload: CompanyCreate[]
  ): Promise<{ created: number; skipped: number; errors: string[] }> =>
    apiClient.post('/companies/batch', payload, { timeout: 120_000 }).then((r) => r.data),
};
