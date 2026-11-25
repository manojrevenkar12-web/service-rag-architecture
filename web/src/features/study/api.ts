export type Metrics = Record<string, number | null> & { byKind?: never };
export type Design = { id: string; label: string; kind: string; mean: Record<string, number | null> };
export type Gate = { id: string; label: string; value: number | null; limit: string; pass: boolean };
export type Report = { kind: string; seeds: number[]; questionsPerSeed: number; chunksPerSeed: number; designs: Design[]; gates: Gate[] };
export type Bench = { machine: string; retrievalMs: { p50: number; p95: number }; pgvector: null | { rows: number; k: number; hnswRecall: number; p50Ms: number; p95Ms: number; exactP95Ms: number } };
export type Study = { dev: Report; heldout: Report | null; bench: Bench | null };

export async function getStudy(): Promise<Study> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/study.json`);
  if (!res.ok) throw new Error("No study results yet. Run `sra lab dev` to generate them.");
  return res.json();
}

export const SHORT: Record<string, string> = {
  "model-alone": "The model alone",
  "naive-rag": "Naive RAG",
  platform: "Platform",
  "fixed-chunks": "Fixed 800-character chunks",
  "vector-only": "Vector search only",
  "keyword-only": "Keyword search only",
  "no-filters": "No product and edition filters",
  "no-reranker": "No reranker",
  "no-verifier": "No verifier",
  "no-tools": "No ERP stock tool",
  "no-guardrails": "No safety and unknown-product guards",
  "top-10": "Reads 10 passages instead of 5",
};
