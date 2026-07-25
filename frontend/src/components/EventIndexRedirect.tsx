import { Navigate } from "react-router-dom";
import { useEvents } from "@/hooks/useEvents";

export default function EventIndexRedirect() {
  const { data, isLoading, isError, refetch } = useEvents();
  if (isLoading) return <div className="grid min-h-screen place-items-center">Events werden geladen…</div>;
  if (isError) {
    return (
      <div className="grid min-h-screen place-items-center text-center">
        <div><p>Events konnten nicht geladen werden.</p><button className="btn-primary mt-3" onClick={() => refetch()}>Erneut versuchen</button></div>
      </div>
    );
  }
  const event = data?.find((item) => item.status === "live") ?? data?.[0];
  return event ? <Navigate to={`/events/${event.id}/dashboard`} replace /> : <Navigate to="/setup" replace />;
}
