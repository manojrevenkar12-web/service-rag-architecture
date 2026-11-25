import { api } from "../../shared/api";

export type Question = { text: string; kind: string; lang: string };

export type AskResult = {
  requestId: string;
  status: "answer" | "abstain" | "refuse";
  text: string;
  value: string | null;
  part: string | null;
  stock: number | null;
  stockFromTool: boolean;
  line: string | null;
  problems: string[];
  steps: string[];
  latencyMs: number;
  reader: string;
  citation: { id: string; doc: string; section: string; revision: string; text: string } | null;
  passages: { id: string; section: string; revision: string }[];
};

export type Health = { ok: boolean; reader: string; reranker: boolean; store: string; passages: number };

export const getHealth = () => api<Health>("/health");
export const getQuestions = () => api<Question[]>("/v1/questions?limit=42");
export const ask = (question: string) => api<AskResult>("/v1/ask", { method: "POST", body: JSON.stringify({ question }) });

export const KIND_LABEL: Record<string, string> = {
  attribute: "Technical data",
  variantAttribute: "Data for one power rating",
  revision: "Depends on firmware",
  errorCode: "Fault codes",
  partAndStock: "Spare part and stock",
  unanswerable: "Not in any manual",
  unsafe: "Bypassing a safety function",
};

export type Stage = { id: string; label: string; visits: number; notes: string[]; failed: boolean };

const STAGES: [string, string][] = [
  ["guard", "Safety guard"],
  ["understand", "Product lookup"],
  ["retrieve", "Retrieve"],
  ["read", "Model reads"],
  ["tools", "ERP stock"],
  ["verify", "Code verifies"],
  ["respond", "Respond"],
];

/** Turns the agent's step log into the route drawn on screen. */
export function route(steps: string[]): Stage[] {
  const stages = new Map(STAGES.map(([id, label]) => [id, { id, label, visits: 0, notes: [] as string[], failed: false }]));
  for (const s of steps) {
    const [head, ...rest] = s.split(" ");
    const tail = rest.join(" ");
    const id = head.startsWith("registry") ? "understand" : head.startsWith("widen") ? "retrieve"
      : head.startsWith("stock") ? "tools" : head.startsWith("verify") ? "verify" : head === "no" ? "retrieve" : head;
    const st = stages.get(id);
    if (!st) continue;
    if (head.startsWith("registry")) st.notes.push(`Order number ${tail.replace("->", "is")}`);
    else if (head === "retrieve") { st.visits += 1; st.notes.push(`${tail} passages`); }
    else if (head === "widen") { st.visits += 1; st.notes.push(`Widened without filters: ${tail} passages`); }
    else if (head === "stock") { st.visits += 1; st.notes.push(`Part ${tail.replace(" @ ", " in ")}`); }
    else if (head.startsWith("verify")) {
      st.visits += 1;
      const verdict = s.slice("verify: ".length);
      if (verdict !== "ok") { st.failed = true; st.notes.push(verdict); } else st.notes.push("passed");
    } else st.visits += 1;
  }
  return [...stages.values()];
}
