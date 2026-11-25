import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { Empty, ErrorState, Loading } from "../../shared/ui/States";
import { ask, getHealth, getQuestions, KIND_LABEL, route, type AskResult, type Question } from "./api";
import { Passage } from "./Passage";
import { RouteStrip } from "./RouteStrip";
import "./ask.css";

export function AskView() {
  const questions = useQuery({ queryKey: ["questions"], queryFn: getQuestions, retry: false });
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const run = useMutation({ mutationFn: ask });
  const [draft, setDraft] = useState("");
  const submit = (q: string) => {
    if (q.trim().length < 3) return;
    setDraft(q);
    run.mutate(q);
  };

  return (
    <div className="ask">
      <aside className="ask-side" aria-label="Questions">
        <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(draft); }}>
          <label htmlFor="q">Question from the field</label>
          <textarea id="q" rows={3} value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="Welches Anzugsdrehmoment hat der VD-340?" />
          <button type="submit" disabled={run.isPending || draft.trim().length < 3}>Ask</button>
          {health.data && health.data.reader === "simulated-llm" && (
            <p className="composer-note">Demo reader: the simulated model knows only the questions listed below.</p>
          )}
        </form>
        <div className="question-wrap"><QuestionList state={questions} onPick={submit} active={run.variables} /></div>
      </aside>
      <section className="ask-main" aria-live="polite">
        {run.isIdle && <Empty title="No question yet" detail="Pick a question on the left or type one. The answer shows the passage it came from and every step the assistant took." />}
        {run.isPending && <Loading label="Retrieving passages and checking the answer" />}
        {run.isError && <ErrorState title="The question could not be answered" detail={run.error.message}
          action={<button type="button" onClick={() => run.variables && run.mutate(run.variables)}>Try again</button>} />}
        {run.data && <Result r={run.data} />}
      </section>
    </div>
  );
}

function QuestionList({ state, onPick, active }: { state: ReturnType<typeof useQuery<Question[]>>; onPick: (q: string) => void; active?: string }) {
  if (state.isPending) return <Loading label="Loading sample questions" />;
  if (state.isError) return <ErrorState title="Sample questions are unavailable" detail={state.error.message} />;
  if (!state.data.length) return <Empty title="No manuals ingested" detail="Run `sra ingest` for this tenant, then reload." />;
  const groups = Object.entries(Object.groupBy(state.data, (q) => q.kind));
  return (
    <div className="questions">
      {groups.map(([kind, qs]) => (
        <section key={kind}>
          <h2>{KIND_LABEL[kind] ?? kind}</h2>
          <ul>
            {qs!.map((q) => (
              <li key={q.text}>
                <button type="button" lang={q.lang} aria-pressed={active === q.text} onClick={() => onPick(q.text)}>{q.text}</button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

const STATUS = {
  answer: { label: "Verified answer", tone: "verified" },
  abstain: { label: "No answer given", tone: "abstain" },
  refuse: { label: "Refused", tone: "refuse" },
} as const;

function Result({ r }: { r: AskResult }) {
  const still = useReducedMotion();
  const s = STATUS[r.status];
  return (
    <AnimatePresence mode="wait">
      <motion.article key={r.requestId} className={`result ${s.tone}`}
        initial={still ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        <header className="plate">
          <p className="plate-status">{s.label}</p>
          {r.value && <p className="plate-value tabular">{r.value}</p>}
          {r.status !== "answer" && <p className="plate-text">{r.text}</p>}
          {r.part && (
            <p className="plate-part">
              Spare part <strong>{r.part}</strong>
              {r.stock !== null && <> with <strong className="tabular">{r.stock}</strong> in stock, read from the ERP</>}
            </p>
          )}
          <p className="plate-meta tabular">{r.reader} answered in {r.latencyMs.toFixed(0)} ms</p>
        </header>
        <RouteStrip stages={route(r.steps)} runKey={r.requestId} />
        {r.citation ? (
          <div className="evidence">
            <h3>Cited passage, edition {r.citation.revision}</h3>
            <Passage text={r.citation.text} line={r.line} />
          </div>
        ) : r.status !== "refuse" && r.passages.length > 0 ? (
          <p className="evidence-none">None of the {r.passages.length} passages read states the answer, so the assistant says so instead of guessing.</p>
        ) : null}
        {r.passages.length > 0 && (
          <details className="read">
            <summary>Passages read ({r.passages.length})</summary>
            <ol>{r.passages.map((p) => <li key={p.id}><span className="tabular">{p.id}</span> {p.section}, edition {p.revision}</li>)}</ol>
          </details>
        )}
      </motion.article>
    </AnimatePresence>
  );
}
