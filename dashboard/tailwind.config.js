/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Terminal-botten: rent svart som referensen (Uncle Bud-dashboarden)
        base: {
          950: "#000000",
          900: "#121212",
          800: "#1A1A1A",
          700: "#242424",
          600: "#333333",
        },
        // Guld - temat är bokstavligen XAU (guld), så accenten är motiverad av ämnet
        gold: {
          400: "#E8C778",
          500: "#D4A94F",
          600: "#B8892E",
        },
        // Semantiska handelsfärger
        buy: "#34D399",
        sell: "#F43F5E",
        neutral: "#8A8F98",
        // Chip-accenter för sekundära ikon-badges (sparklines/icon-chips), i stil
        // med referensdashboardens blå/lila/rosa rotation
        chip: {
          blue: "#5B8DEF",
          purple: "#A78BFA",
        },
      },
      fontFamily: {
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: ["'Inter'", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(212, 169, 79, 0.15)",
      },
    },
  },
  plugins: [],
};
