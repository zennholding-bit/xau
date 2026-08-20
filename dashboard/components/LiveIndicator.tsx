"use client";

import { useEffect, useState } from "react";

/**
 * Visar en pulsande "LIVE"-indikator + hur många sekunder sedan senaste
 * lyckade datahämtningen. Utan den här syns inte att sidan faktiskt pollar
 * i bakgrunden var 15:e sekund (se page.tsx) - man vet bara vad man ser,
 * inte OM det uppdateras.
 */
export default function LiveIndicator({ lastUpdated }: { lastUpdated: Date | null }) {
  const [secondsAgo, setSecondsAgo] = useState<number | null>(null);

  useEffect(() => {
    if (!lastUpdated) return;
    const tick = () => setSecondsAgo(Math.round((Date.now() - lastUpdated.getTime()) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [lastUpdated]);

  return (
    <div className="flex items-center gap-1.5 text-[11px] text-neutral px-2.5 py-1.5 rounded-2xl bg-base-900 border border-white/[0.06]">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-buy opacity-60" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-buy" />
      </span>
      <span>
        {secondsAgo === null
          ? "Ansluter..."
          : secondsAgo < 3
          ? "Uppdaterad nu"
          : `Uppdaterad för ${secondsAgo}s sedan`}
      </span>
    </div>
  );
}
