import { Link, useParams, type LinkProps } from "react-router";
import { scopeToEvent } from "@/hooks/useEventPath";

/** A Link whose app paths ("/teams/42") resolve under the current event. */
export function EventLink({ to, ...rest }: LinkProps & React.RefAttributes<HTMLAnchorElement>) {
  const { eventId } = useParams();
  const scoped = typeof to === "string" ? scopeToEvent(to, eventId) : to;
  return <Link to={scoped} {...rest} />;
}
