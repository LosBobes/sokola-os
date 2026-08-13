// base.css is imported FIRST, before <App> pulls in any component stylesheet.
// In dev, Vite injects each stylesheet as a <style> tag in module-evaluation
// order, so importing it last put the foundational .card/.btn rules AFTER the
// component modifiers that are meant to override them (a `.card` modifier such
// as .home-priority-card--lead has equal specificity, so source order decides).
// Production bundling happened to order it the other way, which made the bug
// invisible in `vite build` and only wrong in the dev server.
import "./styles/base.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SessionProvider } from "./auth/session";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider>
        <App />
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
