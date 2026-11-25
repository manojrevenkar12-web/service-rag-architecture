import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { AskView } from "../features/ask/AskView";
import { StudyView } from "../features/study/StudyView";
import "./app.css";

const client = new QueryClient();
type View = "ask" | "study";

export function App({ initial = "ask" }: { initial?: View }) {
  const [view, setView] = useState<View>(() => (location.hash === "#study" ? "study" : initial));
  const go = (v: View) => { setView(v); history.replaceState(null, "", v === "study" ? "#study" : "#"); };
  return (
    <QueryClientProvider client={client}>
      <header className="bar-top">
        <p className="brand">Service assistant <span>for field service</span></p>
        <nav aria-label="Views">
          <button type="button" aria-current={view === "ask" ? "page" : undefined} onClick={() => go("ask")}>Ask the manuals</button>
          <button type="button" aria-current={view === "study" ? "page" : undefined} onClick={() => go("study")}>Study results</button>
        </nav>
      </header>
      <main className="page">{view === "ask" ? <AskView /> : <StudyView />}</main>
    </QueryClientProvider>
  );
}
