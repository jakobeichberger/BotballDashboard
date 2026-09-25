import type { Config } from "tailwindcss";

/**
 * Text-colour tokens. The shades below are the ones the UI uses for secondary
 * and status text; as text they resolve to CSS variables (src/index.css) that
 * meet WCAG AA (4.5:1) on the light and the dark surfaces. Backgrounds, borders
 * and icons keep the stock palette. A re-theme only changes the variables.
 */
const textToken = (name: string) => `rgb(var(--text-${name}) / <alpha-value>)`;
const TEXT_TOKENS = {
  gray: { 400: textToken("gray-400"), 500: textToken("gray-500") },
  red: { 500: textToken("red-500"), 600: textToken("red-600") },
  amber: { 600: textToken("amber-600") },
  yellow: { 600: textToken("yellow-600") },
  green: { 600: textToken("green-600") },
  blue: { 600: textToken("blue-600") },
  primary: { 600: textToken("primary-600") },
};

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
          950: "#172554",
        },
      },
      textColor: TEXT_TOKENS,
      placeholderColor: { gray: TEXT_TOKENS.gray },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
