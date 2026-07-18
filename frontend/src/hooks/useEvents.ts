import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { EventSummary } from "@/api/types";

export function useEvents() {
  return useQuery<EventSummary[]>({
    queryKey: ["events"],
    queryFn: async () => (await api.get("/v1/events")).data,
  });
}

export function useEvent(eventId?: string) {
  return useQuery<EventSummary>({
    queryKey: ["events", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}`)).data,
    enabled: !!eventId,
  });
}
