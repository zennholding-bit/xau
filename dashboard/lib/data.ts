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
  pendingTrades: number;
};

export function computeKpis(trades: PaperTrade[], signals: Signal[], account: AccountState | null): Kpis {
  // Pending = fortfarande öppen. Closed = har ett exit_time - oavsett vilket
  // exakt outcome-värde (WIN/LOSS/EXPIRED/BREAKEVEN), avgörs vunnen/förlorad
  // av pnl_sek:s tecken. Det gör t.ex. en EXPIRED-trade (tidsgränsen slog
  // till, se max_hold_minutes) som råkade gå plus korrekt räknad som vunnen,
  // istället för att osynligt falla bort ur statistiken helt.
  const pending = trades.filter((t) => t.outcome === "OPEN");
  const closed = trades.filter((t) => t.outcome !== "OPEN" && t.exit_time);
  const wins = closed.filter((t) => (t.pnl_sek ?? 0) > 0);
  const losses = closed.filter((t) => (t.pnl_sek ?? 0) <= 0);

  const totalPnl = closed.reduce((sum, t) => sum + (t.pnl_sek ?? 0), 0);
  const winRate = closed.length > 0 ? (wins.length / closed.length) * 100 : 0;

  return {
    balance: account?.balance_sek ?? 100000,
    totalPnl,
    winRate,
    totalSignals: signals.length,
    tradesTaken: trades.length,
    winningTrades: wins.length,
    losingTrades: losses.length,
    pendingTrades: pending.length,
  };
}

/** Statusen för en enskild trade, för användning i UI-labels (t.ex. SignalCard). */
export type TradeStatus = "WON" | "LOST" | "PENDING";

export function tradeStatus(trade: PaperTrade): TradeStatus {
  if (trade.outcome === "OPEN") return "PENDING";
  return (trade.pnl_sek ?? 0) > 0 ? "WON" : "LOST";
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

/** Rullande win-rate (%) i kronologisk ordning, för sparkline på Win Rate-kortet. */
export function computeWinRateSeries(trades: PaperTrade[]): number[] {
  const closed = trades
    .filter((t) => t.outcome !== "OPEN" && t.exit_time)
    .sort((a, b) => new Date(a.exit_time!).getTime() - new Date(b.exit_time!).getTime());

  const series: number[] = [];
  let wins = 0;
  closed.forEach((t, i) => {
    if ((t.pnl_sek ?? 0) > 0) wins += 1;
    series.push((wins / (i + 1)) * 100);
  });
  return series;
}
