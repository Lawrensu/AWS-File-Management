"use client";

import Link from "next/link";
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { ask } from "@/lib/api";
import { citationHref, parseAnswer } from "@/lib/citations";
import type { AskResponse } from "@/lib/types";
import Header from "@/components/Header";
import { useDepartment } from "@/components/DepartmentSelect";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "done"; response: AskResponse };

function Answer({ response }: { response: AskResponse }) {
  return (
    <p className="whitespace-pre-wrap leading-relaxed">
      {parseAnswer(response.answer, response.citations).map((seg, i) =>
        seg.kind === "text" ? (
          <span key={i}>{seg.text}</span>
        ) : (
          <Link
            key={i}
            href={citationHref(seg.citation)}
            title={`${seg.citation.title}, page ${seg.citation.page}`}
            aria-label={`Source ${seg.n}: ${seg.citation.title}, page ${seg.citation.page}`}
            className="mx-0.5 inline-block rounded bg-blue-100 px-1.5 align-baseline text-xs font-medium text-blue-700 hover:bg-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:hover:bg-blue-900"
          >
            {seg.n}
          </Link>
        ),
      )}
    </p>
  );
}

export default function AskPage() {
  const [department, setDepartment] = useDepartment();
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  const loading = state.kind === "loading";
  const canSubmit = !loading && question.trim() !== "";

  async function submit() {
    const q = question.trim();
    if (!q || loading) return;
    setState({ kind: "loading" });
    try {
      const response = await ask({ question: q, filters: { department } });
      setState({ kind: "done", response });
    } catch (e: unknown) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : "Unknown error",
      });
    }
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void submit();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Header department={department} onDepartmentChange={setDepartment} />
      <main className="mx-auto w-full max-w-2xl flex-1 p-6">
        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
            placeholder="Tanya soalan / Ask a question..."
            aria-label="Question"
            className="w-full rounded border border-zinc-300 bg-white px-3 py-2 text-base outline-none focus:border-blue-500 dark:border-zinc-700 dark:bg-zinc-900"
          />
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-zinc-500">
              Enter to ask, Shift+Enter for a new line
            </span>
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Ask
            </button>
          </div>
        </form>

        <div className="mt-6 space-y-4">
          {state.kind === "loading" && (
            <p className="text-sm text-zinc-500" role="status">
              Thinking...
            </p>
          )}
          {state.kind === "error" && (
            <p
              role="alert"
              className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
            >
              Ask failed: {state.message}
            </p>
          )}
          {state.kind === "done" && state.response.not_found && (
            <p className="whitespace-pre-wrap rounded border border-zinc-200 bg-zinc-100 p-4 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
              {state.response.answer}
            </p>
          )}
          {state.kind === "done" && !state.response.not_found && (
            <>
              <Answer response={state.response} />
              {state.response.citations.length > 0 && (
                <section aria-label="Sources">
                  <h2 className="mb-2 text-sm font-semibold text-zinc-600 dark:text-zinc-400">
                    Sources
                  </h2>
                  <ul className="space-y-1">
                    {state.response.citations.map((c) => (
                      <li key={c.n}>
                        <Link
                          href={citationHref(c)}
                          className="flex items-baseline gap-2 rounded px-2 py-1 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-900"
                        >
                          <span className="shrink-0 font-medium text-blue-700 dark:text-blue-300">
                            [{c.n}]
                          </span>
                          <span className="min-w-0 flex-1 truncate">
                            {c.title}
                          </span>
                          <span className="shrink-0 text-xs text-zinc-500">
                            page {c.page}
                          </span>
                          {c.status === "superseded" && (
                            <span className="shrink-0 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-950 dark:text-red-300">
                              Superseded
                            </span>
                          )}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
