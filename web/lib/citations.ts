import type { Citation } from "./types";

export type AnswerSegment =
  | { kind: "text"; text: string }
  | { kind: "cite"; n: number; citation: Citation };

/** Viewer URL for a citation. Same shape as ResultCard links. */
export function citationHref(c: Citation): string {
  return `/doc/${encodeURIComponent(c.doc_id)}?page=${c.page}&highlight=${encodeURIComponent(c.chunk_id)}`;
}

/**
 * Split answer text into plain text and [n] citation segments.
 * A marker with no matching citation stays in the text as-is.
 * Pure and stateless, so it can run on a partial string while streaming.
 */
export function parseAnswer(
  answer: string,
  citations: Citation[],
): AnswerSegment[] {
  const byN = new Map<number, Citation>();
  for (const c of citations) if (!byN.has(c.n)) byN.set(c.n, c);

  const segments: AnswerSegment[] = [];
  let buffer = "";
  let last = 0;
  const re = /\[(\d+)\]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(answer)) !== null) {
    const citation = byN.get(Number(m[1]));
    buffer += answer.slice(last, m.index);
    last = m.index + m[0].length;
    if (citation) {
      if (buffer) segments.push({ kind: "text", text: buffer });
      buffer = "";
      segments.push({ kind: "cite", n: citation.n, citation });
    } else {
      buffer += m[0];
    }
  }
  buffer += answer.slice(last);
  if (buffer) segments.push({ kind: "text", text: buffer });
  return segments;
}
