import { supabase, Signal, PaperTrade, AccountState } from "./supabase";

export type DateRangeKey = "today" | "7d" | "30d" | "month" | "3m" | "all";

export function rangeToStartDate(range: DateRangeKey): Date | null {
  const now = new Date();
  switch (range) {
    case "today": {
      const d = new Date(now);
      d.setHours(0, 0, 0, 0);
      return d;
    }
    case "7d":
      return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    case "30d":
      return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    case "month":
      return new Date(now.getFullYear(), now.getMonth(), 1);
    case "3m":
      return new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
    case "all":
    default:
      return null;
  }
}

export async function fetchAccountState(): Promise<AccountState | null> {
  const { data, error } = await supabase
    .from("account_state")
    .select("balance_sek, starting_balance_sek")
    .eq("id", 1)
    .single();
  if (error) {
    console.error("fetchAccountState error", error);
    return null;
  }
  return data as AccountState;
}

export async function fetchSignals(startDate: Date | null, limit = 200): Promise<Signal[]> {
  let query = supabase.from("signals").select("*").order("created_at", { ascending: false }).limit(limit);
  if (startDate) query = query.gte("created_at", startDate.toISOString());
  const { data, error } = await query;
  if (error) {
    console.error("fetchSignals error", error);
    return [];
  }
  return (data ?? []) as Signal[];
}

export async function fetchTrades(startDate: Date | null): Promise<PaperTrade[]> {
  let query = supabase.from("paper_trades").select("*").order("entry_time", { ascending: true });
  if (startDate) query = query.gte("entry_time", startDate.toISOString());
  const { data, error } = await query;
  if (error) {
    console.error("fetchTrades error", error);
    return [];
  }
  return (data ?? []) as PaperTrade[];
}

export type Kpis = {
  balance: number;
  totalPnl: number;
  winRate: number;
  totalSignals: number;
  tradesTaken: number;
  winningTrades: number;
  losingTrades: number;
  avgRR: number;
  profitFactor: number;
  maxDrawdownPct: number;
};

export function computeKpis(trades: PaperTrade[], signals: Signal[], account: AccountState | null): Kpis {
  const closed = trades.filter((t) => t.outcome === "WIN" || t.outcome === "LOSS" || t.outcome === "BREAKEVEN");
  const wins = closed.filter((t) => t.outcome === "WIN");
  const losses = closed.filter((t) => t.outcome === "LOSS");

  const totalPnl = closed.reduce((sum, t) => sum + (t.pnl_sek ?? 0), 0);
  const grossWin = wins.reduce((sum, t) => sum + (t.pnl_sek ?? 0), 0);
  const grossLoss = Math.abs(losses.reduce((sum, t) => sum + (t.pnl_sek ?? 0), 0));

  const winRate = closed.length > 0 ? (wins.length / closed.length) * 100 : 0;
  const avgRR =
    closed.length > 0 ? closed.reduce((sum, t) => sum + (t.r_multiple ?? 0), 0) / closed.length : 0;
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0;

  // Max drawdown baserat på kontosaldo-sekvensen från stängda trades
  let peak = -Infinity;
  let maxDD = 0;
  let running = account?.starting_balance_sek ?? 100000;
  for (const t of trades) {
    if (t.account_balance_after != null) running = t.account_balance_after;
    if (running > peak) peak = running;
    const dd = peak > 0 ? ((peak - running) / peak) * 100 : 0;
    if (dd > maxDD) maxDD = dd;
  }

  return {
    balance: account?.balance_sek ?? 100000,
    totalPnl,
    winRate,
    totalSignals: signals.length,
    tradesTaken: closed.length + trades.filter((t) => t.outcome === "OPEN").length,
    winningTrades: wins.length,
    losingTrades: losses.length,
    avgRR,
    profitFactor,
    maxDrawdownPct: maxDD,
  };
}

export type EquityPoint = { time: string; balance: number };

export function computeEquityCurve(trades: PaperTrade[], startingBalance: number): EquityPoint[] {
  const closed = trades
    .filter((t) => t.exit_time && t.account_balance_after != null)
    .sort((a, b) => new Date(a.exit_time!).getTime() - new Date(b.exit_time!).getTime());

  const points: EquityPoint[] = [{ time: "Start", balance: startingBalance }];
  for (const t of closed) {
    points.push({ time: new Date(t.exit_time!).toLocaleString("sv-SE"), balance: t.account_balance_after! });
  }
  return points;
}
