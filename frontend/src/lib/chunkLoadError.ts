/**
 * A lazily loaded chunk could not be fetched — typically a new release was
 * deployed while the tab was open (old hashed files are gone) or the device
 * went offline. Reloading fetches the current index.html and chunks.
 */
export function isChunkLoadError(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /ChunkLoadError|Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(text);
}
