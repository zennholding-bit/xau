"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
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

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
        <XAxis dataKey="time" hide />
        <YAxis
          domain={["auto", "auto"]}
          tick={{ fill: "#7A8494", fontSize: 11, fontFamily: "IBM Plex Mono" }}
          axisLine={false}
          tickLine={false}
          width={70}
          tickFormatter={(v) => `${Math.round(v).toLocaleString("sv-SE")}`}
        />
        <Tooltip
          contentStyle={{
            background: "#161B24",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8,
            fontSize: 12,
            fontFamily: "IBM Plex Mono",
          }}
          labelStyle={{ color: "#7A8494" }}
          formatter={(v: number) => [`${v.toLocaleString("sv-SE")} SEK`, "Saldo"]}
        />
        <Line
          type="monotone"
          dataKey="balance"
          stroke={positive ? "#3DDC84" : "#F0553C"}
          strokeWidth={2}
          dot={false}
          animationDuration={600}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
