export interface CollectionRun {
  id: string;
  company_id: string;
  collector_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
  metadata_json: Record<string, unknown> | null;
}
