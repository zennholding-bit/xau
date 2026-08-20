import { PaperTrade, Signal } from "@/lib/supabase";
import { tradeStatus } from "@/lib/data";

function symbolChip(symbol: string) {
  // Ikon-chip per instrument, i samma anda som referensens färgade fyrkantiga
  // ikon-avatarer i händelselistan - en unik accent per symbol istället för
  // en generisk enfärgad prick.
  if (symbol === "XAUUSD") return { label: "Au", cls: "bg-gold-500/15 text-gold-400" };
  if (symbol === "BTCUSD") return { label: "₿", cls: "bg-chip-purple/15 text-chip-purple" };
  return { label: symbol.slice(0, 2), cls: "bg-chip-blue/15 text-chip-blue" };
}

function statusBadge(status: "WON" | "LOST" | "PENDING") {
  if (status === "WON") return { label: "WON", cls: "bg-buy/10 text-buy" };
  if (status === "LOST") return { label: "LOST", cls: "bg-sell/10 text-sell" };
  return { label: "PENDING", cls: "bg-gold-500/10 text-gold-400" };
}

export default function SignalCard({ signal, trade }: { signal: Signal; trade?: PaperTrade }) {
  const time = new Date(signal.created_at).toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" });
  const chip = symbolChip(signal.symbol);
  const badge = trade ? statusBadge(tradeStatus(trade)) : null;
  const decisionColor =
    signal.decision === "BUY" ? "text-buy" : signal.decision === "SELL" ? "text-sell" : "text-neutral";

  const subtitle =
    signal.decision === "NO_TRADE"
      ? signal.short_explanation ?? "Inget tillräckligt starkt score."
      : trade?.exit_price != null
      ? `${signal.entry?.toFixed(2)} → ${trade.exit_price.toFixed(2)} · ${(trade.pnl_sek ?? 0) >= 0 ? "+" : ""}${trade.pnl_sek?.toFixed(0)} SEK`
      : `Entry ${signal.entry?.toFixed(2)} · SL ${signal.stop_loss?.toFixed(2)} · TP ${signal.take_profit?.toFixed(2)}`;

  return (
    <div className="flex items-center gap-3 px-2 py-2.5 rounded-xl hover:bg-white/[0.03] transition-colors">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 font-bold text-sm ${chip.cls}`}>
        {chip.label}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-white truncate">{signal.symbol}</span>
          <span className={`text-[11px] font-bold ${decisionColor}`}>{signal.decision.replace("_", " ")}</span>
          {badge && (
            <span className={`text-[9px] font-bold tracking-wide px-1.5 py-0.5 rounded-full ${badge.cls}`}>
              {badge.label}
            </span>
          )}
        </div>
        <p className="text-[11px] text-neutral truncate mt-0.5">{subtitle}</p>
      </div>
      <div className="text-right shrink-0">
        <div className="text-[11px] text-neutral tabular">{time}</div>
        <div className="text-[10px] text-gold-400 tabular">{signal.confidence?.toFixed(0)}%</div>
      </div>
    </div>
  );
}
