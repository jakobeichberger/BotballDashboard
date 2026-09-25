import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import i18n from "@/i18n/config";

/**
 * A lazily loaded chunk could not be fetched — typically a new release was
 * deployed while the tab was open (old hashed files are gone) or the device
 * went offline. Reloading fetches the current index.html and chunks.
 */
export function isChunkLoadError(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /ChunkLoadError|Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(text);
}

interface Props {
  children: ReactNode;
  /** When this value changes (e.g. the route), a shown error is cleared. */
  resetKey?: unknown;
  /** Full-screen fallback for the app shell; inline for page content. */
  fullScreen?: boolean;
}

interface State {
  error: Error | null;
}

/**
 * Catches render errors so one broken page does not blank the whole app.
 * Texts go through i18n.t directly: the boundary must work even when the
 * failing component is the one providing translations context.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Render error", error, info.componentStack);
  }

  componentDidUpdate(previous: Props) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const chunk = isChunkLoadError(error);
    return (
      <div className={this.props.fullScreen ? "grid min-h-screen place-items-center bg-gray-50 p-6 dark:bg-gray-950" : "p-6"}>
        <div role="alert" className="card mx-auto max-w-lg p-6 text-center">
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-amber-500" aria-hidden="true" />
          <h1 className="text-lg font-semibold">{i18n.t(chunk ? "common:errorBoundary.chunkTitle" : "common:errorBoundary.title")}</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            {i18n.t(chunk ? "common:errorBoundary.chunkText" : "common:errorBoundary.text")}
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <button type="button" className="btn-primary min-h-11" onClick={() => window.location.reload()}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" /> {i18n.t("common:errorBoundary.reload")}
            </button>
            {!chunk && (
              <button type="button" className="btn-secondary min-h-11" onClick={() => this.setState({ error: null })}>
                {i18n.t("common:retry")}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }
}
