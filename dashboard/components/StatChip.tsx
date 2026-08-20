type Props = {
  icon: React.ReactNode;
  value: string | number;
  label: string;
  accent: "buy" | "sell" | "gold" | "blue";
};

const ACCENT_CLASSES: Record<Props["accent"], string> = {
  buy: "bg-buy/10 text-buy",
  sell: "bg-sell/10 text-sell",
  gold: "bg-gold-500/10 text-gold-400",
  blue: "bg-chip-blue/10 text-chip-blue",
};

export default function StatChip({ icon, value, label, accent }: Props) {
  return (
    <div className="flex items-center gap-3 bg-base-900 border border-white/[0.06] rounded-2xl px-4 py-3 flex-1 min-w-0">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${ACCENT_CLASSES[accent]}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-lg font-bold text-white tabular leading-none">{value}</div>
        <div className="text-[11px] text-white/60 truncate mt-1">{label}</div>
      </div>
    </div>
  );
}
