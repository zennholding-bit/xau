import { PaperTrade, Signal } from "@/lib/supabase";

const DATE_FMT = new Intl.DateTimeFormat("sv-SE", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function symbolChip(symbol: string) {
  if (symbol === "XAUUSD") return { label: "Au", cls: "bg-gold-500/15 text-gold-400" };
  if (symbol === "BTCUSD") return { label: "₿", cls: "bg-chip-purple/15 text-chip-purple" };
  return { label: symbol.slice(0, 2), cls: "bg-chip-blue/15 text-chip-blue" };
}

function directionPill(direction: "BUY" | "SELL") {
  return direction === "BUY"
    ? { label: "LONG", cls: "bg-buy/15 text-buy" }
    : { label: "SHORT", cls: "bg-sell/15 text-sell" };
}

function strategyLabel(strategyMode?: string | null) {
  if (strategyMode === "range") return "Mean Reversion";
  return "Trend Follow";
}

/**
 * En rad i OPEN/CLOSED-listan, i stil med referensbilden: symbol + LONG/SHORT-
 * pill överst, strategi-etikett under, datumintervall längst ner - och till
 * höger R:R / % / $ staplat, färgat efter resultat.
 */
export default function SignalCard({ trade, signal }: { trade: PaperTrade; signal?: Signal }) {
  const chip = symbolChip(trade.symbol);
  const dirPill = directionPill(trade.direction);
  const isOpen = trade.outcome === "OPEN";
  const isWin = !isOpen && (trade.pnl_sek ?? 0) > 0;
  const resultColor = isOpen ? "text-gold-400" : isWin ? "text-buy" : "text-sell";

  const entryDate = DATE_FMT.format(new Date(trade.entry_time));
  const exitDate = trade.exit_time ? DATE_FMT.format(new Date(trade.exit_time)) : null;
  const dateRange = exitDate ? `${entryDate} – ${exitDate}` : `Öppnad ${entryDate}`;

  // R:R: planerad (från entry/SL/TP) om öppen, annars den faktiskt realiserade (r_multiple)
  const plannedRR =
    Math.abs(trade.take_profit - trade.entry_price) / Math.abs(trade.entry_price - trade.stop_loss);
  const rr = isOpen ? plannedRR : trade.r_multiple ?? plannedRR;

  return (
    <div className="flex items-start gap-3 px-2 py-3 border-b border-white/5 last:border-0 hover:bg-white/[0.02] transition-colors">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 font-bold text-xs mt-0.5 ${chip.cls}`}>
        {chip.label}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-white">{trade.symbol}</span>
          <span className={`text-[9px] font-bold tracking-wide px-1.5 py-0.5 rounded ${dirPill.cls}`}>
            {dirPill.label}
          </span>
        </div>
        <p className="text-[12px] text-white/70 mt-1">{strategyLabel(signal?.strategy_mode)}</p>
        <p className="text-[10px] text-neutral mt-0.5">{dateRange}</p>
      </div>
      <div className={`text-right shrink-0 tabular ${resultColor}`}>
        <div className="text-[12px] font-semibold">
          {rr >= 0 ? "+" : ""}
          {rr.toFixed(2)} <span className="text-[9px] font-normal opacity-70">R:R</span>
        </div>
        {isOpen ? (
          <div className="text-[10px] font-medium mt-0.5">PENDING</div>
        ) : (
          <>
            <div className="text-[11px] font-medium mt-0.5">
              {(trade.pnl_pct ?? 0) >= 0 ? "+" : ""}
              {trade.pnl_pct?.toFixed(2)} %
            </div>
            <div className="text-[11px] font-semibold mt-0.5">
              {(trade.pnl_sek ?? 0) >= 0 ? "+" : ""}
              {trade.pnl_sek?.toFixed(0)} SEK
            </div>
          </>
        )}
      </div>
    </div>
  );
}
