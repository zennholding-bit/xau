type Props = {
  label: string;
  value: string;
  tone?: "neutral" | "positive" | "negative";
  hint?: string;
};

export default function KpiCard({ label, value, tone = "neutral", hint }: Props) {
  const toneColor =
    tone === "positive" ? "text-buy" : tone === "negative" ? "text-sell" : "text-gold-400";

  return (
    <div className="bg-base-900 border border-white/[0.07] rounded-lg px-4 py-3 flex flex-col gap-1 min-w-0">
      <span className="text-[11px] uppercase tracking-wider text-neutral font-medium">{label}</span>
      <span className={`tabular text-2xl font-semibold ${toneColor} truncate`}>{value}</span>
      {hint && <span className="text-[11px] text-neutral">{hint}</span>}
    </div>
  );
}
