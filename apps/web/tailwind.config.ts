import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B132B",
        paper: "#F8FAFC",
        pine: "#0F2942",
        "pine-2": "#059669",
        sand: "#D4AF37",
        clay: "#B45309",
        mist: "rgba(255,255,255,0.7)",
        ice: "#1E3A8A",
        earth: "#94A3B8",
        gold: {
          light: "#FDF6B2",
          DEFAULT: "#D4AF37",
          dark: "#B89025",
        },
        navy: {
          light: "#1E3A8A",
          DEFAULT: "#0F2942",
          dark: "#091726",
        },
        obsidian: "#0A0F1D",
      },
      boxShadow: {
        luxury: "0 10px 30px -5px rgba(15, 23, 42, 0.08), 0 0 0 1px rgba(226, 232, 240, 0.9)",
        "luxury-lg": "0 20px 45px -10px rgba(15, 23, 42, 0.12), 0 0 0 1px rgba(212, 175, 55, 0.2)",
        gold: "0 4px 20px -2px rgba(212, 175, 55, 0.35)",
        navy: "0 4px 20px -2px rgba(15, 41, 66, 0.4)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "-apple-system", "sans-serif"],
        serif: ["var(--font-sans)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        frost: "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
