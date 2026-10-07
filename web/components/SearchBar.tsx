"use client";

import { useState, type FormEvent } from "react";

interface SearchBarProps {
  initialQuery?: string;
  disabled?: boolean;
  onSubmit: (query: string) => void;
}

export default function SearchBar({
  initialQuery = "",
  disabled = false,
  onSubmit,
}: SearchBarProps) {
  const [value, setValue] = useState(initialQuery);

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = value.trim();
    if (q) onSubmit(q);
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2" role="search">
      <input
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Cari dokumen / Search documents..."
        aria-label="Search query"
        className="flex-1 rounded border border-zinc-300 bg-white px-3 py-2 text-base outline-none focus:border-blue-500 dark:border-zinc-700 dark:bg-zinc-900"
      />
      <button
        type="submit"
        disabled={disabled || value.trim() === ""}
        className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
      >
        Search
      </button>
    </form>
  );
}
