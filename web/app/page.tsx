"use client";

import { useEffect, useState } from "react";
import { USE_MOCK, health, search } from "@/lib/api";
import type { SearchResult } from "@/lib/types";
import Header from "@/components/Header";
import SearchBar from "@/components/SearchBar";
import ResultCard from "@/components/ResultCard";
import { useDepartment } from "@/components/DepartmentSelect";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "done"; results: SearchResult[] };

export default function Home() {
  const [department, setDepartment] = useDepartment();
  const [query, setQuery] = useState<string | null>(null);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [apiStatus, setApiStatus] = useState("API: checking...");

  useEffect(() => {
    if (USE_MOCK) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setApiStatus("API: mock mode");
      return;
    }
    health()
      .then((h) => setApiStatus(`API: ok, ${h.documents} documents`))
      .catch((e: unknown) =>
        setApiStatus(e instanceof Error ? e.message : "Unknown error"),
      );
  }, []);

  useEffect(() => {
    if (query === null) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ kind: "loading" });
    search({ query, filters: { department } })
      .then((r) => r.results)
      .then((results) => {
        if (!cancelled) setState({ kind: "done", results });
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setState({
            kind: "error",
            message: e instanceof Error ? e.message : "Unknown error",
          });
      });
    return () => {
      cancelled = true;
    };
  }, [query, department]);

  return (
    <div className="flex min-h-screen flex-col">
      <Header department={department} onDepartmentChange={setDepartment} />
      <main className="mx-auto w-full max-w-2xl flex-1 p-6">
        <SearchBar
          disabled={state.kind === "loading"}
          onSubmit={(q) => setQuery(q)}
        />
        <div className="mt-6 space-y-3">
          {state.kind === "loading" && (
            <p className="text-sm text-zinc-500">Searching...</p>
          )}
          {state.kind === "error" && (
            <p
              role="alert"
              className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
            >
              Search failed: {state.message}
            </p>
          )}
          {state.kind === "done" && state.results.length === 0 && (
            <p className="text-sm text-zinc-500">
              No results found / Tiada keputusan.
            </p>
          )}
          {state.kind === "done" &&
            state.results.map((r) => (
              <ResultCard key={r.chunk_id} result={r} />
            ))}
        </div>
      </main>
      <footer className="px-6 py-3 text-xs text-zinc-500">{apiStatus}</footer>
    </div>
  );
}
