import type {
  AskRequest,
  AskResponse,
  Document,
  DocumentDetail,
  HealthResponse,
  SearchRequest,
  SearchResponse,
} from "./types";
import mockSearch from "../mock/search.json";
import mockDocuments from "../mock/documents.json";

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";

const MOCK_DOCS = mockDocuments as unknown as Record<string, DocumentDetail>;

export class ApiError extends Error {
  status: number | null;
  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(`API not reachable at ${BASE_URL}`);
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body.error === "string") message = body.error;
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(message, res.status);
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
  if (USE_MOCK) return Promise.resolve({ ok: true, documents: 3, chunks: 6 });
  return request<HealthResponse>("/health");
}

export function search(req: SearchRequest): Promise<SearchResponse> {
  if (USE_MOCK) return Promise.resolve(mockSearch as SearchResponse);
  return post<SearchResponse>("/search", req);
}

const MOCK_ASK: AskResponse = {
  answer:
    "Ya, kontraktor layak menuntut elaun perjalanan pada kadar RM0.70/km [1].",
  language: "ms",
  confidence: "high",
  citations: [
    {
      n: 1,
      chunk_id: "a1b2c3d4e5f60718:4:1",
      doc_id: "a1b2c3d4e5f60718",
      title: "Pekeliling Perbendaharaan Bil. 3/2024",
      page: 4,
      status: "current",
      quote:
        "kadar elaun perjalanan bagi kontraktor adalah RM0.70 bagi setiap kilometer",
    },
  ],
  not_found: false,
};

export function ask(req: AskRequest): Promise<AskResponse> {
  if (USE_MOCK) return Promise.resolve(MOCK_ASK);
  return post<AskResponse>("/ask", { ...req, stream: false });
}

export async function documents(): Promise<Document[]> {
  if (USE_MOCK) {
    return Object.values(MOCK_DOCS).map((d) => {
      const doc = { ...d };
      delete doc.chunks;
      return doc;
    });
  }
  const data = await request<{ documents: Document[] }>("/documents");
  return data.documents;
}

export function document(id: string): Promise<DocumentDetail> {
  if (USE_MOCK) {
    const doc = MOCK_DOCS[id];
    return doc
      ? Promise.resolve(doc)
      : Promise.reject(new ApiError("Document not found", 404));
  }
  return request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`);
}

export function pageImageUrl(
  docId: string,
  page: number,
  highlightChunkId?: string,
): string {
  if (USE_MOCK) return "/mock/page.svg";
  const url = `${BASE_URL}/documents/${encodeURIComponent(docId)}/pages/${page}.png`;
  return highlightChunkId
    ? `${url}?highlight=${encodeURIComponent(highlightChunkId)}`
    : url;
}
