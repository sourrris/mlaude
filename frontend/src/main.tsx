import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";
import { DiagnosticsPage } from "./diagnostics/DiagnosticsPage.tsx";

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<App />} />
      <Route path="/diagnostics" element={<DiagnosticsPage />} />
    </Routes>
  </BrowserRouter>
);
