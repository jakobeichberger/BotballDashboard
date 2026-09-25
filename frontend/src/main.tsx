import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import { createQueryClient } from "./lib/queryClient";
import { i18nReady } from "./i18n/config";
import "./index.css";

const queryClient = createQueryClient();

function render() {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <ErrorBoundary fullScreen>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </ErrorBoundary>
    </React.StrictMode>
  );
}

// Render once the active language is loaded (one small chunk, precached by the
// service worker); a failed load still renders, falling back to the keys.
i18nReady.then(render, render);
