import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import App from "./App.tsx";
import { DdragonProvider } from "./ddragon/useDdragon.tsx";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <DdragonProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </DdragonProvider>
    </QueryClientProvider>
  </StrictMode>,
);
