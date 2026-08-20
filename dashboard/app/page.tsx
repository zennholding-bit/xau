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

  const latestSignals = signals.slice(0, 30);
  const tradeBySignalId = useMemo(() => {
    const map = new Map<number, PaperTrade>();
    for (const t of trades) {
      if (t.signal_id != null) map.set(t.signal_id, t);
    }
    return map;
  }, [trades]);

  return (
    <main className="h-screen overflow-hidden flex flex-col px-4 md:px-8 py-4 max-w-[1700px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-end gap-3 mb-3 shrink-0">
        <LiveIndicator lastUpdated={lastUpdated} />
        <DateFilter value={range} onChange={setRange} />
      </header>

      {error && (
        <div className="mb-3 rounded-lg bg-sell/[0.08] px-4 py-3 text-sm text-sell shrink-0">
          Kunde inte hämta data: {error}. Kontrollera att NEXT_PUBLIC_SUPABASE_URL och
          NEXT_PUBLIC_SUPABASE_ANON_KEY är korrekt satta i Vercel.
        </div>
      )}

      {/* Huvudlayout: hela sidan är låst till skärmhöjden (h-screen + overflow-
          hidden på <main>) - INGEN sidskroll. Höger kolumn (Latest Signals)
          har sin egen interna scroll (overflow-y-auto) istället, så man
          scrollar i rutan, inte på hela sidan. Vänster kolumn har min-h-0 så
          equity-kortet kan krympa vid behov snarare än att tvinga fram scroll. */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_400px] gap-4 items-stretch flex-1 min-h-0">
        {/* VÄNSTER KOLUMN */}
        <div className="flex flex-col gap-3 min-w-0 min-h-0">
          {/* Hero-kort med sparklines */}
          <section className="grid grid-cols-1 sm:grid-cols-3 gap-3 shrink-0">
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

          {/* Sekundära stora stat-kort */}
          <section className="grid grid-cols-1 sm:grid-cols-2 gap-3 shrink-0">
            <div className="bg-base-900 border border-white/10 rounded-lg px-5 py-3">
              <div className="tabular text-2xl font-bold text-white">{kpis.tradesTaken}</div>
              <div className="text-[13px] text-neutral mt-1">Trades taken totalt</div>
            </div>
            <div className="bg-base-900 border border-white/10 rounded-lg px-5 py-3">
              <div className="tabular text-2xl font-bold text-white">{kpis.totalSignals}</div>
              <div className="text-[13px] text-neutral mt-1">Signaler genererade</div>
            </div>
          </section>

          {/* Ikon-chip-rad: Won / Lost / Pending */}
          <section className="flex flex-col sm:flex-row gap-3 shrink-0">
            <StatChip icon={<CheckIcon />} value={kpis.winningTrades} label="Won" accent="buy" />
            <StatChip icon={<XIcon />} value={kpis.losingTrades} label="Lost" accent="sell" />
            <StatChip icon={<ClockIcon />} value={kpis.pendingTrades} label="Pending" accent="gold" />
          </section>

          {/* Equity curve - flex-1 + min-h-0 så den fyller kvarvarande utrymme
              och krymper vid behov istället för att trycka ut sidan i scroll */}
          <div className="bg-base-900 border border-white/10 rounded-lg p-5 flex-1 flex flex-col min-h-0">
            <h2 className="flex items-center justify-between text-[15px] font-bold text-white mb-3 shrink-0">
              Equity Curve
              <span className="text-neutral"><SignalIcon /></span>
            </h2>
            <div className="flex-1 min-h-0">
              <EquityChart data={equity} />
            </div>
          </div>
        </div>

        {/* HÖGER KOLUMN: Latest Signals, full höjd, intern scroll */}
        <div className="bg-base-900 border border-white/10 rounded-lg p-5 flex flex-col min-h-0">
          <h2 className="flex items-center justify-between text-[15px] font-bold text-white mb-3 shrink-0">
            Latest Signals
            <span className="text-neutral"><ListIcon /></span>
          </h2>
          <div className="flex flex-col overflow-y-auto flex-1 min-h-0 pr-1">
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
      </div>
    </main>
  );
}
