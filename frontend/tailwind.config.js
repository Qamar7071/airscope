/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0b0d10",
          900: "#13161b",
          850: "#181c22",
          800: "#1d222a",
          700: "#2a3039",
          600: "#3a414c",
        },
        brand: {
          300: "#7ee7f5",
          400: "#38d3ec",
          500: "#13b8d6",
          600: "#0e93ad",
        },
        txt: {
          primary: "#eef0f3",
          secondary: "#b4bac4",
          muted: "#7f8792",
        },
        status: {
          good: "#0ca30c",
          warning: "#fab219",
          serious: "#ec835a",
          critical: "#d03b3b",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        panel: "0 10px 30px -10px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.06)",
        glow: "0 0 0 1px rgba(56,211,236,0.35), 0 0 24px -4px rgba(56,211,236,0.45)",
      },
      keyframes: {
        pulseRing: {
          "0%": { transform: "scale(0.6)", opacity: "0.9" },
          "100%": { transform: "scale(2.2)", opacity: "0" },
        },
      },
      animation: {
        "pulse-ring": "pulseRing 2.2s cubic-bezier(0.2, 0.6, 0.4, 1) infinite",
      },
    },
  },
  plugins: [],
};
