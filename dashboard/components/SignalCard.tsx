import { Signal } from "@/lib/supabase";

function decisionColor(decision: string) {
  if (decision === "BUY") return "text-buy border-buy/30 bg-buy/[0.06]";
  if (decision === "SELL") return "text-sell border-sell/30 bg-sell/[0.06]";
  return "text-neutral border-white/10 bg-white/[0.03]";
}

export default function SignalCard({ signal }: { signal: Signal }) {
  const time = new Date(signal.created_at).toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" });

  return (
    <div className={`rounded-lg border px-3 py-3 flex flex-col gap-2 ${decisionColor(signal.decision)}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold tracking-wide">{signal.symbol}</span>
        <span className="text-xs font-bold tabular">{signal.decision.replace("_", " ")}</span>
      </div>

      {signal.decision !== "NO_TRADE" ? (
        <div className="tabular text-[11px] text-neutral grid grid-cols-2 gap-x-3 gap-y-0.5">
          <span>Entry</span>
          <span className="text-right text-white/90">{signal.entry?.toFixed(2)}</span>
          <span>SL</span>
          <span className="text-right text-white/90">{signal.stop_loss?.toFixed(2)}</span>
          <span>TP</span>
          <span className="text-right text-white/90">{signal.take_profit?.toFixed(2)}</span>
          <span>R:R</span>
          <span className="text-right text-white/90">{signal.risk_reward?.toFixed(2)}</span>
        </div>
      ) : (
        <p className="text-[11px] text-neutral leading-snug line-clamp-2">{signal.short_explanation}</p>
      )}

      <div className="flex items-center justify-between text-[11px] text-neutral">
        <span>Confidence: <span className="tabular text-gold-400">{signal.confidence?.toFixed(0)}%</span></span>
        <span className="tabular">{time}</span>
      </div>
    </div>
  );
}
