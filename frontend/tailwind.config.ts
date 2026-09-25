import type { Config } from "tailwindcss";

/**
 * Design tokens (WehrFlow design DNA). Every themed value is a CSS variable in
 * src/index.css holding RGB channels, so `bg-flaeche`, `text-leise`, … switch
 * with the theme (`.dark` on <html>) without `dark:` variants and still take
 * Tailwind's opacity modifiers (`bg-primary/10`).
 */
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

/**
 * Text-colour tokens. The shades below are the ones the UI uses for secondary
 * and status text; as text they resolve to CSS variables that meet WCAG AA
 * (4.5:1) on the light and the dark surfaces. Backgrounds, borders and icons
 * keep the palette. A re-theme only changes the variables.
 */
const textToken = (name: string) => token(`text-${name}`);
const TEXT_TOKENS = {
  gray: { 400: textToken("gray-400"), 500: textToken("gray-500") },
  red: { 500: textToken("red-500"), 600: textToken("red-600") },
  amber: { 600: textToken("amber-600") },
  yellow: { 600: textToken("yellow-600") },
  green: { 600: textToken("green-600") },
  blue: { 600: textToken("blue-600") },
  primary: {
    400: textToken("primary-600"),
    500: textToken("primary-600"),
    600: textToken("primary-600"),
    700: textToken("primary-600"),
  },
  // Red text that stays AA on every surface (links, active items, errors).
  akzent: textToken("primary-600"),
};

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Signal red scale around #e31823 (--rot); 600 is the brand red.
        primary: {
          DEFAULT: "#e31823",
          50: "#fff1f1",
          100: "#ffe0e1",
          200: "#ffc6c8",
          300: "#ff9ba0",
          400: "#ff5a60", // rot-auf-dunkel
          500: "#ff4d57", // rot-hell
          600: "#e31823", // rot / signal
          700: "#b0121c", // rot-dunkel
          800: "#8f1219",
          900: "#76151b",
          950: "#410608",
        },
        rot: {
          DEFAULT: "#e31823",
          hell: "#ff4d57",
          dunkel: "#b0121c",
          "auf-dunkel": "#ff5a60",
        },
        // Cool neutral scale from the DNA: 50/100 papier, 200 rand, 500 text-leise,
        // 700 rand-dunkel, 900 tief-2, 950 tief. Pages that still use gray-*
        // therefore sit on the same palette as the semantic tokens.
        gray: {
          50: "#f5f6f8",
          100: "#e8eaee",
          200: "#d8dce2",
          300: "#bfc5cd",
          400: "#9aa3ad",
          500: "#666f76",
          600: "#4b535c",
          700: "#2a3038",
          800: "#22262e",
          900: "#1a1d23",
          950: "#0d0f13",
        },
        papier: { DEFAULT: token("papier"), 2: token("papier-2") },
        flaeche: { DEFAULT: token("flaeche"), 2: token("flaeche-2") },
        tief: { DEFAULT: "#0d0f13", 2: "#1a1d23", 3: "#16181d" },
        // The sidebar is dark in both themes (text-invers tokens of the DNA).
        sidebar: { DEFAULT: "#1a1d23", text: "#dfe3e8", leise: "#9aa3ad", rand: "#2a3038" },
        fg: token("text"),
        leise: token("text-leise"),
        rand: { DEFAULT: token("rand"), stark: token("rand-stark"), dunkel: "#2a3038" },
        success: token("success"),
        warning: token("warning"),
        danger: token("danger"),
        info: token("info"),
      },
      textColor: TEXT_TOKENS,
      placeholderColor: { gray: TEXT_TOKENS.gray },
      borderRadius: {
        DEFAULT: "var(--radius)",
        karte: "var(--radius)",
        eng: "var(--radius-eng)",
      },
      boxShadow: {
        flach: "var(--schatten)",
        tief: "var(--schatten-tief)",
        ember: "var(--schatten-ember)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ['"Exo 2"', "Inter", "system-ui", "sans-serif"],
        ui: ['"Geist Sans"', "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        display: "-0.035em",
        ui: "-0.01em",
        overline: "0.1em",
      },
      transitionTimingFunction: {
        DEFAULT: "cubic-bezier(.16,1,.3,1)",
        wehr: "cubic-bezier(.16,1,.3,1)",
      },
      transitionDuration: {
        DEFAULT: "200ms",
      },
      maxWidth: {
        breite: "68rem",
      },
    },
  },
  plugins: [],
} satisfies Config;
