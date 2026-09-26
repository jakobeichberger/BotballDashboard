import { useNavigate, useParams, type NavigateOptions } from "react-router";

/**
 * App pages live under /events/:eventId/…, but many pages link with plain
 * app paths ("/teams/42", "/papers"). These helpers scope such paths to the
 * event currently being viewed, so a page does not have to thread the event id
 * through every link it renders.
 *
 * Paths that are already global — /events/…, /login, /public/…, /setup,
 * /settings — pass through unchanged, as does anything relative.
 */
const GLOBAL_PREFIXES = ["/events/", "/login", "/public/", "/setup", "/settings"];

export function scopeToEvent(to: string, eventId: string | undefined): string {
  if (!eventId || !to.startsWith("/")) return to;
  if (GLOBAL_PREFIXES.some((prefix) => to === prefix.replace(/\/$/, "") || to.startsWith(prefix))) {
    return to;
  }
  return `/events/${eventId}${to}`;
}

export function useEventPath(): (to: string) => string {
  const { eventId } = useParams();
  return (to: string) => scopeToEvent(to, eventId);
}

export function useEventNavigate(): (to: string | number, options?: NavigateOptions) => void {
  const navigate = useNavigate();
  const { eventId } = useParams();
  return (to, options) => {
    if (typeof to === "number") navigate(to);
    else navigate(scopeToEvent(to, eventId), options);
  };
}
