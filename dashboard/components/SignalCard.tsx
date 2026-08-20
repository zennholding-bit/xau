import { PaperTrade, Signal } from "@/lib/supabase";
import { tradeStatus } from "@/lib/data";

function decisionColor(decision: string) {
  if (decision === "BUY") return "text-buy border-buy/30 bg-buy/[0.06]";
  if (decision === "SELL") return "text-sell border-sell/30 bg-sell/[0.06]";
  return "text-neutral border-white/10 bg-white/[0.03]";
}

function statusBadge(status: "WON" | "LOST" | "PENDING") {
  if (status === "WON") return { label: "WON", cls: "text-buy border-buy/40 bg-buy/[0.12]" };
  if (status === "LOST") return { label: "LOST", cls: "text-sell border-sell/40 bg-sell/[0.12]" };
  return { label: "PENDING", cls: "text-gold-400 border-gold-500/40 bg-gold-500/[0.10]" };
}

export default function SignalCard({ signal, trade }: { signal: Signal; trade?: PaperTrade }) {
  const time = new Date(signal.created_at).toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" });
  const badge = trade ? statusBadge(tradeStatus(trade)) : null;

  return (
    <div className={`rounded-lg border px-3 py-3 flex flex-col gap-2 ${decisionColor(signal.decision)}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold tracking-wide">{signal.symbol}</span>
        <div className="flex items-center gap-1.5">
          {badge && (
            <span className={`text-[10px] font-bold tracking-wide px-1.5 py-0.5 rounded border ${badge.cls}`}>
              {badge.label}
            </span>
          )}
          <span className="text-xs font-bold tabular">{signal.decision.replace("_", " ")}</span>
        </div>
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
          {trade?.exit_price != null && (
            <>
              <span>Exit</span>
              <span className="text-right text-white/90">{trade.exit_price.toFixed(2)}</span>
              <span>P&L</span>
              <span className={`text-right font-semibold ${(trade.pnl_sek ?? 0) >= 0 ? "text-buy" : "text-sell"}`}>
                {(trade.pnl_sek ?? 0) >= 0 ? "+" : ""}
                {trade.pnl_sek?.toFixed(0)} SEK
              </span>
            </>
          )}
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
