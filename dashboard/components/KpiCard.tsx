import Sparkline from "./Sparkline";

type Props = {
  label: string;
  value: string;
  tone?: "neutral" | "positive" | "negative";
  hint?: string;
  sparkline?: number[];
  badge?: string;
};

export default function KpiCard({ label, value, tone = "neutral", hint, sparkline, badge }: Props) {
  const toneColor =
    tone === "positive" ? "text-buy" : tone === "negative" ? "text-sell" : "text-white";
  const sparkColor = tone === "positive" ? "#34D399" : tone === "negative" ? "#F43F5E" : "#5B8DEF";

  return (
    <div className="bg-base-900 border border-white/10 rounded-lg px-5 py-4 flex flex-col gap-2 min-w-0">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[15px] font-bold text-white/80">{label}</span>
        {sparkline && <Sparkline data={sparkline} color={sparkColor} />}
      </div>
      <div className="flex items-end justify-between gap-2">
        <span className={`tabular text-2xl font-bold ${toneColor} truncate`}>{value}</span>
        {badge && (
          <span
            className={`text-[11px] font-semibold px-2 py-0.5 rounded-full shrink-0 ${
              tone === "negative" ? "bg-sell/10 text-sell" : "bg-buy/10 text-buy"
            }`}
          >
            {badge}
          </span>
        )}
      </div>
      {hint && <span className="text-[11px] text-neutral">{hint}</span>}
    </div>
  );
}
