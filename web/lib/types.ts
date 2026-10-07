// Hand-written mirror of contracts/api.md and contracts/document.schema.json.

export type Status = "current" | "superseded" | "draft";
export type Lang = "ms" | "en" | "mixed";
export type DocType =
  | "circular"
  | "policy"
  | "sop"
  | "guideline"
  | "report"
  | "meeting_minutes"
  | "form"
  | "letter"
  | "other";
export type Confidence = "high" | "medium" | "low";

export interface Document {
  doc_id: string;
  title: string;
  filename: string;
  source_path?: string;
  doc_type: DocType;
  department: string;
  topics?: string[];
  year?: number | null;
  lang: Lang;
  status: Status;
  supersedes?: string[];
  superseded_by?: string | null;
  keywords?: string[];
  page_count: number;
  has_scanned_pages?: boolean;
  ingested_at?: string;
}

export interface SearchFilters {
  department?: string | null;
  doc_type?: DocType | null;
  include_superseded?: boolean;
}

export interface SearchRequest {
  query: string;
  filters?: SearchFilters;
  top_k?: number;
}

export interface SearchResult {
  chunk_id: string;
  doc_id: string;
  title: string;
  page: number;
  snippet: string;
  score: number;
  doc_type: DocType;
  department: string;
  status: Status;
  superseded_by: string | null;
  lang: Lang;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface AskRequest {
  question: string;
  filters?: SearchFilters;
  top_k?: number;
  stream?: boolean;
}

export interface Citation {
  n: number;
  chunk_id: string;
  doc_id: string;
  title: string;
  page: number;
  status: Status;
  quote: string;
}

export interface AskResponse {
  answer: string;
  language: Lang;
  confidence: Confidence;
  citations: Citation[];
  not_found: boolean;
}

export interface UploadResponse {
  doc_id: string;
  title: string;
  pages: number;
  chunks: number;
  status: Status;
  department: string;
}

export interface HealthResponse {
  ok: boolean;
  documents: number;
  chunks: number;
}

// Chunk as returned by GET /documents/{id} (contracts/chunk.schema.json, embedding omitted).
export interface Chunk {
  chunk_id: string;
  doc_id: string;
  page: number;
  bbox?: number[] | null;
  heading?: string | null;
  text: string;
  lang: Lang;
  source: "native" | "textract" | "vision";
}

export interface DocumentDetail extends Document {
  chunks?: Chunk[];
}
