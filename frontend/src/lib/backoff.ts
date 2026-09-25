/**
 * Exponential backoff with jitter, for reconnects and retries: a random delay
 * in [base·2^attempt / 2, base·2^attempt], capped at `max`. The jitter keeps
 * many clients (e.g. every scoreboard screen after a server restart) from
 * reconnecting in lock-step.
 */
export function backoffDelay(attempt: number, base = 500, max = 10_000, random = Math.random): number {
  const ceiling = Math.min(max, base * 2 ** attempt);
  return Math.round(ceiling / 2 + random() * (ceiling / 2));
}
