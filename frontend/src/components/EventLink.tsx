import { forwardRef } from "react";
import { Link, useParams, type LinkProps } from "react-router-dom";
import { scopeToEvent } from "@/hooks/useEventPath";

/** A Link whose app paths ("/teams/42") resolve under the current event. */
export const EventLink = forwardRef<HTMLAnchorElement, LinkProps>(function EventLink(
  { to, ...rest },
  ref,
) {
  const { eventId } = useParams();
  const scoped = typeof to === "string" ? scopeToEvent(to, eventId) : to;
  return <Link ref={ref} to={scoped} {...rest} />;
});
