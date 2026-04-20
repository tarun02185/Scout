export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  metadata?: MessageMetadata;
}

export interface MessageMetadata {
  sql_used?: string | null;
  sources_used?: string[];
  intent?: { intent?: string };
  has_chart?: boolean;
  chart_data?: ChartData | null;
}

export interface ChartData {
  columns: string[];
  rows: Record<string, unknown>[];
  dtypes: Record<string, string>;
}

export interface FileUploadResult {
  file: string;
  status: 'success' | 'error' | 'already_uploaded';
  metadata?: SourceMetadata;
  error?: string;
  pii_warnings?: string[];
}

export interface SourceMetadata {
  source_name: string;
  source_type: 'structured' | 'document' | 'image' | 'log' | 'database' | 'url';
  table_name?: string;
  row_count?: number;
  column_count?: number;
  columns?: { name: string; type: string }[];
  chunk_count?: number;
  page_count?: number;
  image_count?: number;
  line_count?: number;
  table_count?: number;
  width?: number;
  height?: number;
  // URL-sourced metadata
  url?: string;
  pages_crawled?: number;
  chunks?: number;
}

export interface QueryResponse {
  response: string;
  chart_data: ChartData | null;
  sql_used: string | null;
  sources_used: string[];
  intent: { intent?: string };
}
