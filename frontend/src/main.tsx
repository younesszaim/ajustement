import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import "./styles.css";
import "./history.css";
import "./global.css";
import "./visibility.css";
import "./navigation.css";
import "./batch.css";
import "./batch-preview.css";
import "./adjustment-dialog.css";
import "./lineage.css";
import "./search-lineage.css";
import "./workspace-actions.css";
import "./revert.css";
import "./cacib-theme.css";
import "./dialog-layer.css";
import "./destructive-actions.css";
import "./register-links.css";
import "./trade-history.css";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: 1, staleTime: 15000 } },
        })
      }
    >
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
