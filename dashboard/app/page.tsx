"use client";

import { useEffect, useMemo, useState } from "react";
import KpiCard from "@/components/KpiCard";
import StatChip from "@/components/StatChip";
import LiveIndicator from "@/components/LiveIndicator";
import EquityChart from "@/components/EquityChart";
import SignalCard from "@/components/SignalCard";
import DateFilter from "@/components/DateFilter";
import {
  DateRangeKey,
  rangeToStartDate,
  fetchAccountState,
  fetchSignals,
  fetchTrades,
  computeKpis,
  computeEquityCurve,
  computeWinRateSeries,
} from "@/lib/data";
import { AccountState, PaperTrade, Signal } from "@/lib/supabase";

const SEK = new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 });

// Ikoner hålls som små inline-SVG:er (ingen extra icon-dependency) - i samma
// stil som de fyrkantiga färgade ikon-chipsen i referensdashboarden.
const CheckIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const XIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const ClockIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const SignalIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <path d="M4 20h16M6 16v4M12 10v10M18 4v16" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const ListIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function DashboardPage() {
  const [range, setRange] = useState<DateRangeKey>("30d");
  const [loading, setLoading] = useState(true);
  const [account, setAccount] = useState<AccountState | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Auto-refresh: dashboarden hämtade tidigare bara EN gång vid sidladdning
  // och uppdaterades sen aldrig. Pollar nu var 15:e sekund istället - lätt
  // anrop (bara läsning från Supabase), så det finns ingen anledning att
  // vänta på en manuell F5 längre.
  useEffect(() => {
    let cancelled = false;
    const start = rangeToStartDate(range);

    const load = (showSpinner: boolean) => {
      if (showSpinner) setLoading(true);
      setError(null);
      Promise.all([fetchAccountState(), fetchSignals(start), fetchTrades(start)])
        .then(([acc, sig, tr]) => {
          if (cancelled) return;
          setAccount(acc);
          setSignals(sig);
          setTrades(tr);
          setLastUpdated(new Date());
        })
        .catch((e) => {
          if (!cancelled) setError(String(e));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };

    load(true);
    const interval = setInterval(() => load(false), 15000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [range]);

  const kpis = useMemo(() => computeKpis(trades, signals, account), [trades, signals, account]);
  const equity = useMemo(
    () => computeEquityCurve(trades, account?.starting_balance_sek ?? 100000),
    [trades, account]
  );
  const balanceSpark = useMemo(() => equity.map((p) => p.balance), [equity]);
  const winRateSpark = useMemo(() => computeWinRateSeries(trades), [trades]);

  const latestSignals = signals.slice(0, 20);
  const tradeBySignalId = useMemo(() => {
    const map = new Map<number, PaperTrade>();
    for (const t of trades) {
      if (t.signal_id != null) map.set(t.signal_id, t);
    }
    return map;
  }, [trades]);

  return (
    <main className="min-h-screen px-4 md:px-8 py-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gold-500/10 flex items-center justify-center">
            <span className="tabular text-gold-400 font-bold text-base">Au</span>
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">XAU Signal Terminal</h1>
            <p className="text-[11px] text-neutral -mt-0.5">Paper trading · ingen riktig handel</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <LiveIndicator lastUpdated={lastUpdated} />
          <DateFilter value={range} onChange={setRange} />
        </div>
      </header>

      {error && (
        <div className="mb-6 rounded-2xl bg-sell/[0.08] px-4 py-3 text-sm text-sell">
          Kunde inte hämta data: {error}. Kontrollera att NEXT_PUBLIC_SUPABASE_URL och
          NEXT_PUBLIC_SUPABASE_ANON_KEY är korrekt satta i Vercel.
        </div>
      )}

      {/* Hero-kort: Balance / Total P&L / Win Rate - med sparklines, som referensens toppkort */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
        <KpiCard label="Balance" value={`${SEK.format(kpis.balance)} SEK`} sparkline={balanceSpark} />
        <KpiCard
          label="Total P&L"
          value={`${kpis.totalPnl >= 0 ? "+" : ""}${SEK.format(kpis.totalPnl)} SEK`}
          tone={kpis.totalPnl >= 0 ? "positive" : "negative"}
          sparkline={balanceSpark}
          badge={kpis.totalPnl >= 0 ? "↗ Vinst" : "↘ Förlust"}
        />
        <KpiCard
          label="Win Rate"
          value={`${kpis.winRate.toFixed(1)}%`}
          tone={kpis.winRate >= 50 ? "positive" : "neutral"}
          sparkline={winRateSpark}
        />
      </section>

      {/* Sekundära stora stat-kort, som referensens "Average order value" / "Average products per order" */}
      <section className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <div className="bg-base-900 rounded-2xl px-5 py-4">
          <div className="tabular text-3xl font-bold text-white">{kpis.tradesTaken}</div>
          <div className="text-[13px] text-neutral mt-1">Trades taken totalt</div>
        </div>
        <div className="bg-base-900 rounded-2xl px-5 py-4">
          <div className="tabular text-3xl font-bold text-white">{kpis.totalSignals}</div>
          <div className="text-[13px] text-neutral mt-1">Signaler genererade</div>
        </div>
      </section>

      {/* Ikon-chip-rad: Won / Lost / Pending - som referensens Products/Categories/Low stock/Customers-rad */}
      <section className="flex flex-col sm:flex-row gap-3 mb-6">
        <StatChip icon={<CheckIcon />} value={kpis.winningTrades} label="Won" accent="buy" />
        <StatChip icon={<XIcon />} value={kpis.losingTrades} label="Lost" accent="sell" />
        <StatChip icon={<ClockIcon />} value={kpis.pendingTrades} label="Pending" accent="gold" />
      </section>

      {/* Equity + Latest signals */}
      <section className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-4">
        <div className="bg-base-900 rounded-2xl p-5">
          <h2 className="flex items-center gap-2 text-xs uppercase tracking-wider text-neutral font-semibold mb-4">
            <SignalIcon />
            Equity Curve
          </h2>
          <EquityChart data={equity} />
        </div>

        <div className="bg-base-900 rounded-2xl p-5 flex flex-col">
          <h2 className="flex items-center gap-2 text-xs uppercase tracking-wider text-neutral font-semibold mb-2">
            <ListIcon />
            Latest Signals
          </h2>
          <div className="flex flex-col overflow-y-auto max-h-[520px] pr-1">
            {loading && <p className="text-neutral text-sm px-2 py-3">Laddar...</p>}
            {!loading && latestSignals.length === 0 && (
              <p className="text-neutral text-sm px-2 py-3">
                Inga signaler ännu i vald period. Cykeln körs var 5:e minut — vänta eller trigga den manuellt.
              </p>
            )}
            {latestSignals.map((s) => (
              <SignalCard key={s.id} signal={s} trade={tradeBySignalId.get(s.id)} />
            ))}
          </div>
        </div>
      </section>

      <footer className="mt-8 text-center text-[11px] text-neutral">
        Data uppdateras automatiskt. Ingen riktig handel sker i detta system.
      </footer>
    </main>
  );
}
