import { Navigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useEvents } from "@/hooks/useEvents";

export default function EventIndexRedirect() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useEvents();
  if (isLoading) return <div className="grid min-h-screen place-items-center">{t("eventsLoading")}</div>;
  if (isError) {
    return (
      <div className="grid min-h-screen place-items-center text-center">
        <div><p>{t("eventsLoadFailed")}</p><button className="btn-primary mt-3" onClick={() => refetch()}>{t("retry")}</button></div>
      </div>
    );
  }
  const event = data?.find((item) => item.status === "live") ?? data?.[0];
  return event ? <Navigate to={`/events/${event.id}/dashboard`} replace /> : <Navigate to="/setup" replace />;
}
