"use client";

import { useEffect, useMemo, useState } from "react";
import KpiCard from "@/components/KpiCard";
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
} from "@/lib/data";
import { AccountState, PaperTrade, Signal } from "@/lib/supabase";

const SEK = new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 });

export default function DashboardPage() {
  const [range, setRange] = useState<DateRangeKey>("30d");
  const [loading, setLoading] = useState(true);
  const [account, setAccount] = useState<AccountState | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Auto-refresh: dashboarden hämtade tidigare bara EN gång vid sidladdning
  // och uppdaterades sen aldrig - man var tvungen att manuellt ladda om för
  // att se nya trades/signaler, vilket kändes segt även när backend faktiskt
  // hann köra en ny 5-minuters-cykel under tiden. Pollar nu var 15:e sekund
  // istället - lätt anrop (bara läsning från Supabase), så det finns
  // ingen anledning att vänta på en manuell F5 längre.
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

    load(true); // första hämtningen visar loading-spinner
    const interval = setInterval(() => load(false), 15000); // därefter tyst i bakgrunden

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

  const latestSignals = signals.slice(0, 20);

  return (
    <main className="min-h-screen px-4 md:px-8 py-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-gold-500/10 border border-gold-500/30 flex items-center justify-center">
            <span className="tabular text-gold-400 font-bold text-sm">Au</span>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">XAU SIGNAL TERMINAL</h1>
            <p className="text-[11px] text-neutral -mt-0.5">Paper trading · ingen riktig handel</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <LiveIndicator lastUpdated={lastUpdated} />
          <DateFilter value={range} onChange={setRange} />
        </div>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-sell/30 bg-sell/[0.06] px-4 py-3 text-sm text-sell">
          Kunde inte hämta data: {error}. Kontrollera att NEXT_PUBLIC_SUPABASE_URL och
          NEXT_PUBLIC_SUPABASE_ANON_KEY är korrekt satta i Vercel.
        </div>
      )}

      {/* KPI-rad */}
      <section className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 mb-6">
        <KpiCard label="Balance" value={`${SEK.format(kpis.balance)} SEK`} />
        <KpiCard
          label="Total P&L"
          value={`${kpis.totalPnl >= 0 ? "+" : ""}${SEK.format(kpis.totalPnl)} SEK`}
          tone={kpis.totalPnl >= 0 ? "positive" : "negative"}
        />
        <KpiCard label="Win Rate" value={`${kpis.winRate.toFixed(1)}%`} />
        <KpiCard label="Total Signals" value={`${kpis.totalSignals}`} />
        <KpiCard label="Trades Taken" value={`${kpis.tradesTaken}`} />
        <KpiCard label="Avg R:R" value={kpis.avgRR.toFixed(2)} />
        <KpiCard
          label="Profit Factor"
          value={Number.isFinite(kpis.profitFactor) ? kpis.profitFactor.toFixed(2) : "∞"}
        />
        <KpiCard label="Max Drawdown" value={`${kpis.maxDrawdownPct.toFixed(1)}%`} tone="negative" />
      </section>

      {/* Equity + Latest signals */}
      <section className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4">
        <div className="bg-base-900 border border-white/[0.07] rounded-lg p-4">
          <h2 className="text-xs uppercase tracking-wider text-neutral font-semibold mb-4">Equity Curve</h2>
          <EquityChart data={equity} />
        </div>

        <div className="bg-base-900 border border-white/[0.07] rounded-lg p-4 flex flex-col">
          <h2 className="text-xs uppercase tracking-wider text-neutral font-semibold mb-4">Latest Signals</h2>
          <div className="flex flex-col gap-2 overflow-y-auto max-h-[500px] pr-1">
            {loading && <p className="text-neutral text-sm">Laddar...</p>}
            {!loading && latestSignals.length === 0 && (
              <p className="text-neutral text-sm">
                Inga signaler ännu i vald period. GitHub Actions-jobbet körs var 5:e minut —
                vänta eller trigga det manuellt.
              </p>
            )}
            {latestSignals.map((s) => (
              <SignalCard key={s.id} signal={s} />
            ))}
          </div>
        </div>
      </section>

      <footer className="mt-8 text-center text-[11px] text-neutral">
        Data uppdateras automatiskt via GitHub Actions. Ingen riktig handel sker i detta system.
      </footer>
    </main>
  );
}
