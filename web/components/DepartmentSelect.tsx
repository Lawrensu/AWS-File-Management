"use client";

import { useEffect, useState } from "react";
import { DEPARTMENTS } from "@/lib/taxonomy";

export const DEPARTMENT_STORAGE_KEY = "rujuk.department";
export const DEFAULT_DEPARTMENT = "Umum";

/** Viewer department, persisted in localStorage. Reusable by other pages (D6). */
export function useDepartment(): [string, (d: string) => void] {
  const [department, setDepartmentState] = useState<string>(DEFAULT_DEPARTMENT);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(DEPARTMENT_STORAGE_KEY);
      if (saved && (DEPARTMENTS as readonly string[]).includes(saved)) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setDepartmentState(saved);
      }
    } catch {
      // storage unavailable; keep default
    }
  }, []);

  function setDepartment(d: string) {
    setDepartmentState(d);
    try {
      localStorage.setItem(DEPARTMENT_STORAGE_KEY, d);
    } catch {
      // ignore write failures
    }
  }

  return [department, setDepartment];
}

interface DepartmentSelectProps {
  value: string;
  onChange: (department: string) => void;
}

export default function DepartmentSelect({
  value,
  onChange,
}: DepartmentSelectProps) {
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
      <span>Viewing as:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-zinc-300 bg-white px-2 py-1 text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      >
        {DEPARTMENTS.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </select>
    </label>
  );
}
