import { useState } from "react";
import { useOfflineQueue } from "@/hooks/useOfflineQueue";

/**
 * The "saved offline" notice of a score entry page, tied to the queued entry
 * itself: it shows once the entry is queued and disappears as soon as the
 * entry has left the offline queue (synced or discarded), instead of staying
 * on screen after the sync. A newer queued entry replaces the older notice,
 * so there is never more than one.
 */
export function useQueuedNotice() {
  const [tracked, setTracked] = useState<{ id: string; seen: boolean } | null>(null);
  const { entries } = useOfflineQueue();
  const inQueue = !!tracked && entries.some((entry) => entry.id === tracked.id);
  // Remember that the queue listed the entry, so its absence later means "synced"
  // (right after queueing, the list may not have caught up yet).
  if (tracked && inQueue && !tracked.seen) setTracked({ ...tracked, seen: true });
  return {
    visible: !!tracked && (inQueue || !tracked.seen),
    show: (id: string) => setTracked({ id, seen: false }),
    hide: () => setTracked(null),
  };
}
