"use client";

import { DateRangeKey } from "@/lib/data";

const OPTIONS: { key: DateRangeKey; label: string }[] = [
  { key: "today", label: "TODAY" },
  { key: "7d", label: "7D" },
  { key: "30d", label: "30D" },
  { key: "month", label: "MONTH" },
  { key: "3m", label: "3M" },
  { key: "all", label: "ALL" },
];

export default function DateFilter({
  value,
  onChange,
}: {
  value: DateRangeKey;
  onChange: (v: DateRangeKey) => void;
}) {
  return (
    <div className="flex items-center gap-1 bg-base-900 border border-white/[0.06] rounded-2xl p-1">
      {OPTIONS.map((opt) => (
        <button
          key={opt.key}
          onClick={() => onChange(opt.key)}
          className={`px-3 py-1.5 text-xs font-semibold tracking-wide rounded-xl transition-colors ${
            value === opt.key
              ? "bg-gold-500/15 text-gold-400"
              : "text-neutral hover:text-white/80"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
