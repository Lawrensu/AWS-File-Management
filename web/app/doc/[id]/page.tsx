"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ApiError, document as fetchDocument, pageImageUrl } from "@/lib/api";
import type { DocumentDetail } from "@/lib/types";

type Loaded = { id: string; doc: DocumentDetail | null; error?: string };

function Viewer() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();

  const id = params.id;
  const parsed = parseInt(search.get("page") ?? "1", 10);
  const page = Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
  const highlight = search.get("highlight") || undefined;

  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDocument(id)
      .then((doc) => !cancelled && setLoaded({ id, doc }))
      .catch((e: unknown) => {
        if (cancelled) return;
        const error =
          e instanceof ApiError && e.status === 404
            ? "Document not found"
            : e instanceof Error
              ? e.message
              : "Unknown error";
        setLoaded({ id, doc: null, error });
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const shell = (body: React.ReactNode) => (
    <main className="mx-auto flex w-full max-w-[900px] flex-col items-center gap-4 px-4 py-8">
      <div className="w-full">
        <Link href="/" className="text-sm text-blue-700 hover:underline">
          &larr; Back to search
        </Link>
      </div>
      {body}
    </main>
  );

  if (!loaded || loaded.id !== id) {
    return shell(<p className="text-gray-600">Loading...</p>);
  }
  if (!loaded.doc) {
    return shell(<p className="text-gray-800">{loaded.error ?? "Document not found"}</p>);
  }

  const { doc } = loaded;
  const total = doc.page_count;
  const go = (p: number) => router.push(`/doc/${encodeURIComponent(id)}?page=${p}`);
  const src = pageImageUrl(id, page, highlight);
  const btn =
    "rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";

  return shell(
    <>
      <h1 className="text-center text-xl font-semibold">{doc.title}</h1>
      <div className="flex items-center gap-4">
        <button className={btn} disabled={page <= 1} onClick={() => go(page - 1)}>
          Prev
        </button>
        <span className="text-sm">
          Page {page} of {total}
        </span>
        <button className={btn} disabled={page >= total} onClick={() => go(page + 1)}>
          Next
        </button>
      </div>
      {failedSrc === src ? (
        <p className="text-gray-800">Page not available</p>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={src}
          src={src}
          alt={`${doc.title}, page ${page}`}
          className="h-auto w-full max-w-[900px] border border-gray-200"
          onError={() => setFailedSrc(src)}
        />
      )}
    </>,
  );
}

export default function DocPage() {
  return (
    <Suspense fallback={<p className="p-8 text-center text-gray-600">Loading...</p>}>
      <Viewer />
    </Suspense>
  );
}
