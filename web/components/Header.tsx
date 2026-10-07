"use client";

import Link from "next/link";
import DepartmentSelect from "./DepartmentSelect";

interface HeaderProps {
  department: string;
  onDepartmentChange: (department: string) => void;
}

export default function Header({ department, onDepartmentChange }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-zinc-200 px-6 py-3 dark:border-zinc-800">
      <div className="flex items-baseline gap-6">
        <h1 className="text-xl font-semibold">Rujuk</h1>
        <nav aria-label="Main" className="flex gap-4 text-sm">
          <Link href="/" className="hover:text-blue-600">
            Search
          </Link>
          <Link href="/ask" className="hover:text-blue-600">
            Ask
          </Link>
        </nav>
      </div>
      <DepartmentSelect value={department} onChange={onDepartmentChange} />
    </header>
  );
}
