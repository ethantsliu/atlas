import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./font.css";
import "./base.css";
import "./map.css";
import "./cloud.css";
import "./panel.css";
import "./tooltip.css";
import "./pages.css";
import "./responsive.css";
import "./feasibility.css";
import "./insights.css";
import "./brief.css";
import "./paper.css";
import "./dialog.css";
import "./feed.css";
import "./theme.css";
import "./gallery.css";
import "./sheet.css";
import "./type.css";
import "./dark.css";

function mountApp() {
  void document.fonts?.load('400 16px "Libre Baskerville Variable"').catch(() => []);
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

mountApp();
