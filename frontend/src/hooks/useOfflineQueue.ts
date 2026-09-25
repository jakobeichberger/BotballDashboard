import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import {
  QUEUE_CHANGED_EVENT,
  belongsTo,
  claimQueuedScore,
  discardQueuedScore,
  isUnclaimed,
  listQueuedScores,
  retryQueuedScore,
  syncQueuedScores,
  type QueuedScore,
} from "@/lib/offlineQueue";

/** Live view of the offline score queue (IndexedDB). */
export function useOfflineQueue(filter?: (entry: QueuedScore) => boolean) {
  const [entries, setEntries] = useState<QueuedScore[]>([]);
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id ?? null);

  const reload = useCallback(async () => {
    try {
      setEntries(await listQueuedScores());
    } catch {
      // IndexedDB unavailable (private mode): nothing can be queued either.
      setEntries([]);
    }
  }, []);

  useEffect(() => {
    void reload();
    window.addEventListener(QUEUE_CHANGED_EVENT, reload);
    return () => window.removeEventListener(QUEUE_CHANGED_EVENT, reload);
  }, [reload]);

  const sync = useCallback(async () => {
    // Wait until we know who is signed in — entries are replayed as their author.
    if (!userId) return { synced: 0, failed: 0, remaining: 0 };
    const result = await syncQueuedScores(api, userId);
    if (result.synced > 0) await queryClient.invalidateQueries();
    return result;
  }, [queryClient, userId]);

  const retry = useCallback(async (id: string, force = false) => {
    await retryQueuedScore(id, force);
    if (navigator.onLine) await sync();
  }, [sync]);

  // An entry recorded without a known user is sent as the signed-in user only
  // on their explicit request.
  const claim = useCallback(async (id: string) => {
    if (!userId) return;
    await claimQueuedScore(id, userId);
    if (navigator.onLine) await sync();
  }, [sync, userId]);

  const mine = entries.filter((entry) => belongsTo(entry, userId));
  return {
    entries: filter ? mine.filter(filter) : mine,
    retry,
    claim,
    discard: discardQueuedScore,
    sync,
  };
}

/**
 * Replays queued scores on app start and whenever the browser comes back
 * online. Mounted once in the Layout.
 */
export function useOfflineSync() {
  const { entries, sync } = useOfflineQueue();

  useEffect(() => {
    const run = () => { if (navigator.onLine) void sync().catch(() => undefined); };
    run();
    window.addEventListener("online", run);
    // Entries kept after a server error get another chance every minute.
    const timer = window.setInterval(run, 60_000);
    return () => {
      window.removeEventListener("online", run);
      window.clearInterval(timer);
    };
  }, [sync]);

  return {
    pending: entries.filter((entry) => !isUnclaimed(entry) && (entry.status === "pending" || entry.status === "syncing")).length,
    // Unclaimed entries need the user just like failed ones.
    failed: entries.filter((entry) => isUnclaimed(entry) || entry.status === "conflict" || entry.status === "error").length,
  };
}
