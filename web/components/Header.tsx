"use client";

import DepartmentSelect from "./DepartmentSelect";

interface HeaderProps {
  department: string;
  onDepartmentChange: (department: string) => void;
}

export default function Header({ department, onDepartmentChange }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-zinc-200 px-6 py-3 dark:border-zinc-800">
      <h1 className="text-xl font-semibold">Rujuk</h1>
      <DepartmentSelect value={department} onChange={onDepartmentChange} />
    </header>
  );
}
