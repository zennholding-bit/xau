import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL as string;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string;

if (!url || !anonKey) {
  // Kraschar inte builden, men loggar tydligt om nycklarna saknas i produktion.
  console.warn(
    "NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY saknas. " +
      "Lägg in dem som Environment Variables i Vercel."
  );
}

export const supabase = createClient(url ?? "", anonKey ?? "");

export type Signal = {
  id: number;
  signal_uid: string;
  symbol: string;
  created_at: string;
  decision: "BUY" | "SELL" | "NO_TRADE";
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  confidence: number;
  final_score: number;
  technical_score: number;
  fundamental_score: number;
  macro_score: number;
  news_score: number;
  short_explanation: string | null;
  full_reasoning: string | null;
  status: string;
  strategy_mode?: "trend" | "range" | null;
};

export type PaperTrade = {
  id: number;
  signal_id: number | null;
  symbol: string;
  direction: "BUY" | "SELL";
  entry_time: string;
  exit_time: string | null;
  entry_price: number;
  exit_price: number | null;
  stop_loss: number;
  take_profit: number;
  pnl_sek: number | null;
  pnl_pct: number | null;
  r_multiple: number | null;
  lots: number | null;
  outcome: "WIN" | "LOSS" | "BREAKEVEN" | "EXPIRED" | "CANCELLED" | "OPEN";
  account_balance_after: number | null;
};

export type AccountState = {
  balance_sek: number;
  starting_balance_sek: number;
};
