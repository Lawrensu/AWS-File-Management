import type {
  AskRequest,
  AskResponse,
  Document,
  DocumentDetail,
  HealthResponse,
  SearchRequest,
  SearchResponse,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body.error === "string") message = body.error;
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function health(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function search(req: SearchRequest): Promise<SearchResponse> {
  return post<SearchResponse>("/search", req);
}

export function ask(req: AskRequest): Promise<AskResponse> {
  return post<AskResponse>("/ask", { ...req, stream: false });
}

export async function documents(): Promise<Document[]> {
  const data = await request<{ documents: Document[] }>("/documents");
  return data.documents;
}

export function document(id: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`);
}

export function pageImageUrl(
  docId: string,
  page: number,
  highlightChunkId?: string,
): string {
  const url = `${BASE_URL}/documents/${encodeURIComponent(docId)}/pages/${page}.png`;
  return highlightChunkId
    ? `${url}?highlight=${encodeURIComponent(highlightChunkId)}`
    : url;
}
