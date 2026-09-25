import type { ReactNode } from "react";
import clsx from "clsx";

/**
 * Page header of the portal style: bold Exo 2 title, muted subtitle, optional
 * overline above the title and the primary action(s) top right.
 */
export default function PageHeader({
  title,
  subtitle,
  overline,
  actions,
  children,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  overline?: ReactNode;
  /** Buttons/links shown top right (wrap below the title on phones). */
  actions?: ReactNode;
  /** Extra content under the subtitle (badges, meta line). */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <header className={clsx("page-header", className)}>
      <div className="min-w-0">
        {overline && <p className="eyebrow mb-1.5">{overline}</p>}
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
