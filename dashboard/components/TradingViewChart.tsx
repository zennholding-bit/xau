"use client";

import { useEffect, useRef } from "react";

const SYMBOL_MAP: Record<string, string> = {
  XAUUSD: "OANDA:XAUUSD",
};

declare global {
  interface Window {
    TradingView?: {
      widget: new (options: Record<string, unknown>) => unknown;
    };
  }
}

/**
 * TradingViews publika Advanced Chart-widget (gratis, ingen inloggning/API-
 * nyckel behövs - samma embed vem som helst kan lägga på sin hemsida).
 * Laddar tv.js en gång, återanvänder den, och skapar om widgeten varje gång
 * symbolen byts.
 */
export default function TradingViewChart({ symbol }: { symbol: keyof typeof SYMBOL_MAP }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const containerId = `tv_chart_${symbol}`;

  useEffect(() => {
    let cancelled = false;

    const createWidget = () => {
      if (cancelled || !containerRef.current || !window.TradingView) return;
      containerRef.current.innerHTML = "";
      new window.TradingView.widget({
        autosize: true,
        symbol: SYMBOL_MAP[symbol],
        interval: "5",
        timezone: "Etc/UTC",
        theme: "dark",
        style: "1",
        locale: "sv",
        toolbar_bg: "#000000",
        backgroundColor: "#000000",
        gridColor: "rgba(255,255,255,0.06)",
        enable_publishing: false,
        hide_top_toolbar: false,
        hide_legend: false,
        allow_symbol_change: false,
        save_image: false,
        container_id: containerId,
      });
    };

    if (window.TradingView) {
      createWidget();
    } else {
      const existing = document.getElementById("tradingview-widget-script");
      if (existing) {
        existing.addEventListener("load", createWidget);
      } else {
        const script = document.createElement("script");
        script.id = "tradingview-widget-script";
        script.src = "https://s3.tradingview.com/tv.js";
        script.async = true;
        script.onload = createWidget;
        document.body.appendChild(script);
      }
    }

    return () => {
      cancelled = true;
    };
  }, [symbol, containerId]);

  return <div id={containerId} ref={containerRef} className="w-full h-full" />;
}
