/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Terminal-botten: djup, nästan svart blånyans - inte rent svart, inte generisk kall grå
        base: {
          950: "#0A0D12",
          900: "#0F131A",
          800: "#161B24",
          700: "#1F2530",
          600: "#2A3140",
        },
        // Guld - temat är bokstavligen XAU (guld), så accenten är motiverad av ämnet
        gold: {
          400: "#E8C778",
          500: "#D4A94F",
          600: "#B8892E",
        },
        // Semantiska handelsfärger
        buy: "#3DDC84",
        sell: "#F0553C",
        neutral: "#7A8494",
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
