export interface CompanySignal {
  id: string;
  company_id: string;
  source_type: string;
  source_url: string | null;
  signal_type: string;
  signal_text: string;
  numeric_value: number | null;
  confidence: number | null;
  captured_at: string;
  created_at: string;
}
