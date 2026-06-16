import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        void: "#08080E",
        surface: "#0F0F18",
        overlay: "#14141F",
        line: "#1C1C2E",
        "line-bright": "#2E2E4A",
        primary: "#E2E2F0",
        muted: "#5A5A7A",
        dim: "#2E2E4A",
        prism: "#4F7FFF",
        critical: "#FF2D55",
        high: "#FF9500",
        medium: "#FFD60A",
        low: "#32D74B",
        suggest: "#48484A",
      },
      fontFamily: {
        display: ["var(--font-space-mono)", "monospace"],
        heading: ["var(--font-space-mono)", "monospace"],
        body: ["var(--font-geist)", "sans-serif"],
        label: ["var(--font-geist)", "sans-serif"],
        code: ["var(--font-geist-mono)", "monospace"],
        "finding-msg": ["var(--font-geist)", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
