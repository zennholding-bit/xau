"use client";

import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { EquityPoint } from "@/lib/data";

export default function EquityChart({ data }: { data: EquityPoint[] }) {
  if (data.length <= 1) {
    return (
      <div className="h-64 flex items-center justify-center text-neutral text-sm">
        Ingen avslutad trade ännu — equity-kurvan visas här när första trade stängts.
      </div>
    );
  }

  const first = data[0].balance;
  const last = data[data.length - 1].balance;
  const positive = last >= first;
  const color = positive ? "#34D399" : "#F43F5E";

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="time" hide />
        <YAxis
          domain={["auto", "auto"]}
          tick={{ fill: "#8A8F98", fontSize: 11, fontFamily: "IBM Plex Mono" }}
          axisLine={false}
          tickLine={false}
          width={70}
          tickFormatter={(v) => `${Math.round(v).toLocaleString("sv-SE")}`}
        />
        <Tooltip
          contentStyle={{
            background: "#121212",
            border: "none",
            borderRadius: 12,
            fontSize: 12,
            fontFamily: "IBM Plex Mono",
          }}
          labelStyle={{ color: "#8A8F98" }}
          formatter={(v: number) => [`${v.toLocaleString("sv-SE")} SEK`, "Saldo"]}
        />
        <Area
          type="monotone"
          dataKey="balance"
          stroke={color}
          strokeWidth={2.5}
          fill="url(#equityFill)"
          dot={false}
          animationDuration={600}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
