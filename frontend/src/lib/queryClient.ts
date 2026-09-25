import { QueryClient } from "@tanstack/react-query";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
      },
      mutations: {
        // React Query would pause mutations while the browser is offline and
        // leave their buttons spinning. Writes decide for themselves instead
        // (lib/api.ts): score entries go to the offline queue, every other
        // write fails at once with OFFLINE_WRITE_BLOCKED.
        networkMode: "always",
      },
    },
  });
}
