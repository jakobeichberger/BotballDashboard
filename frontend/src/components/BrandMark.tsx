import clsx from "clsx";

/**
 * Brand mark: the robot head of public/icons/app-icon.svg in stroke style
 * (same 64-unit geometry as the favicon and scripts/generate-icons.py). The
 * colour comes from `currentColor`, so callers pick it with a text class.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round">
        <rect x="12" y="17" width="40" height="28" rx="8" />
        <path d="M32 17v-6M8 27v8M56 27v8M26 38h12M32 45v5M21 52h22" />
      </g>
      <g fill="currentColor">
        <circle cx="32" cy="9" r="3.6" />
        <circle cx="24.5" cy="29.5" r="3.8" />
        <circle cx="39.5" cy="29.5" r="3.8" />
      </g>
    </svg>
  );
}

/** Logo badge: the mark on a dark "tief" tile with a hairline ring. */
export function LogoBadge({ size = "md", className }: { size?: "sm" | "md" | "lg"; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-grid shrink-0 place-items-center rounded-full bg-tief text-primary ring-1 ring-white/10",
        size === "sm" && "h-9 w-9",
        size === "md" && "h-11 w-11",
        size === "lg" && "h-16 w-16",
        className,
      )}
      aria-hidden="true"
    >
      <BrandMark className={size === "lg" ? "h-10 w-10" : size === "md" ? "h-7 w-7" : "h-6 w-6"} />
    </span>
  );
}

/**
 * Wordmark "Botball Dashboard": "Botball" in the text colour, "Dashboard" in
 * red, Exo 2 800 with tight tracking (as "Wehr" + "Flow"). `onDark` is for the
 * always-dark sidebar and the big-screen page.
 */
export function Wordmark({ className, onDark = false }: { className?: string; onDark?: boolean }) {
  return (
    <span className={clsx("font-display font-extrabold leading-none tracking-display", className)}>
      <span className={onDark ? "text-white" : "text-fg"}>Botball</span>
      <span className={onDark ? "text-rot-auf-dunkel" : "text-akzent"}>Dashboard</span>
    </span>
  );
}
