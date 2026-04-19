export interface Company {
  id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  company_size: string | null;
  source_added_from: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyCreate {
  name: string;
  domain?: string;
  industry?: string;
  company_size?: string;
  source_added_from?: string;
}
