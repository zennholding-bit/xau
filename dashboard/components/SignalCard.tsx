import { PaperTrade, Signal } from "@/lib/supabase";

const DATE_FMT = new Intl.DateTimeFormat("sv-SE", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

// 1 pip på XAUUSD = $0.01 (den vanligaste konventionen på MT4/MT5, matchar
// "Digits: 2" i kontospecifikationen). Om fler symboler läggs till senare
// behöver den här bli symbol-medveten istället för hårdkodad.
const PIP_SIZE = 0.01;

function directionPill(direction: "BUY" | "SELL") {
  return direction === "BUY"
    ? { label: "LONG", cls: "bg-buy/15 text-buy" }
    : { label: "SHORT", cls: "bg-sell/15 text-sell" };
}

/**
 * En rad i OPEN/CLOSED-listan. Ingen ikon-avatar längre - bara symboltexten
 * (XAUUSD/BTCUSD), större och tydligare stil rakt igenom.
 */
export default function SignalCard({ trade, signal }: { trade: PaperTrade; signal?: Signal }) {
  const dirPill = directionPill(trade.direction);
  const isOpen = trade.outcome === "OPEN";
  const isWin = !isOpen && (trade.pnl_sek ?? 0) > 0;
  const resultColor = isOpen ? "text-gold-400" : isWin ? "text-buy" : "text-sell";

  const entryDate = DATE_FMT.format(new Date(trade.entry_time));
  const exitDate = trade.exit_time ? DATE_FMT.format(new Date(trade.exit_time)) : null;
  const dateRange = exitDate ? `${entryDate} – ${exitDate}` : `Öppnad ${entryDate}`;

  // Pips realiserade (stängd trade) eller pips kvar till TP (öppen trade)
  const realizedPips = trade.exit_price != null
    ? Math.abs(trade.exit_price - trade.entry_price) / PIP_SIZE
    : null;
  const targetPips = Math.abs(trade.take_profit - trade.entry_price) / PIP_SIZE;

  return (
    <div className="flex flex-col gap-1.5 px-2 py-3.5 border-b border-white/5 last:border-0 hover:bg-white/[0.02] transition-colors">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[16px] font-bold text-white">{trade.symbol}</span>
          <span className={`text-[10px] font-bold tracking-wide px-1.5 py-0.5 rounded ${dirPill.cls}`}>
            {dirPill.label}
          </span>
        </div>
        <div className={`text-right shrink-0 tabular ${resultColor}`}>
          {isOpen ? (
            <div className="flex items-baseline gap-2 justify-end">
              <span className="text-[13px] font-semibold">PENDING</span>
              <span className="text-[11px] text-neutral font-medium">mål {targetPips.toFixed(0)} pips</span>
            </div>
          ) : (
            <div className="flex items-baseline gap-2">
              <span
                className={`text-[10px] font-bold tracking-wide px-1.5 py-0.5 rounded ${
                  isWin ? "bg-buy/15 text-buy" : "bg-sell/15 text-sell"
                }`}
              >
                {isWin ? "WON" : "LOST"}
              </span>
              <span className="text-[12px] text-neutral font-medium">{realizedPips?.toFixed(1)} pips</span>
              <span className="text-[13px] font-medium">
                {(trade.pnl_pct ?? 0) >= 0 ? "+" : ""}
                {trade.pnl_pct?.toFixed(2)}%
              </span>
              <span className="text-[14px] font-bold">
                {(trade.pnl_sek ?? 0) >= 0 ? "+" : ""}
                {trade.pnl_sek?.toFixed(0)} SEK
              </span>
            </div>
          )}
        </div>
      </div>

      <p className="tabular text-[13px] text-neutral whitespace-nowrap">
        Entry <span className="text-white/85 font-semibold">{trade.entry_price.toFixed(2)}</span>
        {"  ·  "}SL <span className="text-sell/85 font-semibold">{trade.stop_loss.toFixed(2)}</span>
        {"  ·  "}TP <span className="text-buy/85 font-semibold">{trade.take_profit.toFixed(2)}</span>
        {trade.exit_price != null && (
          <>
            {"  ·  "}Exit{" "}
            <span className={`font-semibold ${isWin ? "text-buy/85" : "text-sell/85"}`}>
              {trade.exit_price.toFixed(2)}
            </span>
          </>
        )}
      </p>

      <p className="text-[11px] text-neutral/80">{dateRange}</p>
    </div>
  );
}
