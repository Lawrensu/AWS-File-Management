"use client";

import Link from "next/link";
import type { SearchResult } from "@/lib/types";

export default function ResultCard({ result }: { result: SearchResult }) {
  const href = `/doc/${encodeURIComponent(result.doc_id)}?page=${result.page}&highlight=${encodeURIComponent(result.chunk_id)}`;
  return (
    <Link
      href={href}
      className="block rounded border border-zinc-200 p-4 hover:border-blue-500 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-medium">{result.title}</h2>
        <span className="shrink-0 text-xs text-zinc-500">page {result.page}</span>
      </div>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        {result.snippet}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
          {result.doc_type}
        </span>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
          {result.department}
        </span>
        {result.status === "superseded" && (
          <span className="rounded-full bg-red-100 px-2 py-0.5 font-medium text-red-700 dark:bg-red-950 dark:text-red-300">
            Superseded
          </span>
        )}
      </div>
    </Link>
  );
}
