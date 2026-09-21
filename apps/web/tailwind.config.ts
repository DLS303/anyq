import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1C1915",
        paper: "#EFE8DE",
        pine: "#2F5B8A",
        "pine-2": "#3E7A62",
        sand: "#B56A43",
        clay: "#C4923A",
        mist: "rgba(255,255,255,0.45)",
        ice: "#2F5B8A",
        earth: "#C9A882",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        serif: ["var(--font-sans)", "system-ui", "sans-serif"],
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
