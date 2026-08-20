"use client";

import { LineChart, Line, ResponsiveContainer } from "recharts";

export default function Sparkline({
  data,
  color,
}: {
  data: number[];
  color: string;
}) {
  if (data.length < 2) return <div className="w-20 h-10" />;

  const points = data.map((v, i) => ({ i, v }));

  return (
    <div className="w-20 h-10">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
