import { useQuery } from "@tanstack/react-query";
import { Empty, ErrorState, Loading } from "../../shared/ui/States";
import { getStudy, SHORT, type Design, type Gate, type Report } from "./api";
import "./study.css";

const pct = (v: number | null | undefined, d = 1) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`);
const num = (v: number | null | undefined, d = 1) => (v == null ? "–" : v.toFixed(d));

export function StudyView() {
  const q = useQuery({ queryKey: ["study"], queryFn: getStudy, retry: false });
  if (q.isPending) return <Loading label="Loading study results" />;
  if (q.isError) return <ErrorState title="Study results are missing" detail={q.error.message} />;
  const { dev, heldout, bench } = q.data;
  if (!dev.designs.length) return <Empty title="No designs in the report" detail="Check config/designs.json and rerun the study." />;
  const by = Object.fromEntries(dev.designs.map((d) => [d.id, d]));
  const platform = by.platform;
  const heads = ["model-alone", "naive-rag", "platform"].map((id) => by[id]).filter(Boolean);
  const ablations = dev.designs.filter((d) => d.kind === "ablation");
  return (
    <div className="study">
      <section className="lede">
        <h1>
          Wrong answers per 1,000 questions from service technicians
        </h1>
        <p className="lede-sub">
          {dev.seeds.length} simulated equipment makers, {dev.questionsPerSeed} questions and {dev.chunksPerSeed.toLocaleString("en")} manual passages each.
          Every design meets the same manuals, the same questions and the same model behaviour.
        </p>
        <WrongBars designs={heads} />
      </section>

      <section>
        <h2>What each part of the platform is worth</h2>
        <p className="section-sub">Each row switches one part off. Correct answers among answerable questions, against the full platform at {pct(platform.mean.correctRate)}.</p>
        <table className="ablations">
          <thead><tr><th scope="col">Change</th><th scope="col">Correct</th><th scope="col">Difference</th><th scope="col">Wrong per 1,000</th><th scope="col">€ per 1,000</th></tr></thead>
          <tbody>
            {ablations.map((d) => <AblationRow key={d.id} d={d} base={platform} />)}
          </tbody>
        </table>
      </section>

      <section className="gates-wrap">
        <GateList title={`Release gates on the dev seeds ${dev.seeds.join(", ")}`} gates={dev.gates} />
        {heldout ? <GateList title={`Held-out seeds ${heldout.seeds.join(", ")}, run once`} gates={heldout.gates} report={heldout} />
          : <Empty title="Held-out not run yet" detail="The held-out seeds are run once, after the design is frozen: `sra lab heldout`." />}
      </section>

      {bench && (
        <section>
          <h2>Measured on this machine</h2>
          <dl className="bench tabular">
            <div><dt>Retrieval in process, p95</dt><dd>{num(bench.retrievalMs.p95)} ms</dd></div>
            {bench.pgvector && <>
              <div><dt>pgvector HNSW recall against exact search</dt><dd>{pct(bench.pgvector.hnswRecall)}</dd></div>
              <div><dt>pgvector query p95 over {bench.pgvector.rows.toLocaleString("en")} passages</dt><dd>{num(bench.pgvector.p95Ms)} ms</dd></div>
            </>}
          </dl>
          <p className="section-sub">{bench.machine}</p>
        </section>
      )}
    </div>
  );
}

function WrongBars({ designs }: { designs: Design[] }) {
  const max = Math.max(...designs.map((d) => d.mean.wrongPer1000 ?? 0), 1);
  return (
    <div className="bars" role="img" aria-label={designs.map((d) => `${SHORT[d.id]}: ${num(d.mean.wrongPer1000)}`).join(", ")}>
      {designs.map((d) => {
        const v = d.mean.wrongPer1000 ?? 0;
        return (
          <div key={d.id} className={`bar-row ${d.kind === "platform" ? "is-platform" : ""}`}>
            <span className="bar-label">{SHORT[d.id]}</span>
            <span className="bar-track" title={`${SHORT[d.id]}: ${num(v)} wrong per 1,000; ${pct(d.mean.correctRate)} correct`}>
              <span className="bar" style={{ width: `${Math.max((v / max) * 100, 0.6)}%` }} />
            </span>
            <span className="bar-value tabular">{num(v)}</span>
            <span className="bar-aside tabular">{pct(d.mean.correctRate)} correct</span>
          </div>
        );
      })}
    </div>
  );
}

function AblationRow({ d, base }: { d: Design; base: Design }) {
  const diff = (d.mean.correctRate ?? 0) - (base.mean.correctRate ?? 0);
  const worse = diff < -0.005;
  return (
    <tr>
      <th scope="row">{SHORT[d.id] ?? d.label}</th>
      <td className="tabular">{pct(d.mean.correctRate)}</td>
      <td className={`tabular ${worse ? "worse" : ""}`}>{diff >= 0 ? "+" : "−"}{Math.abs(diff * 100).toFixed(1)} points</td>
      <td className={`tabular ${(d.mean.wrongPer1000 ?? 0) > 5 ? "worse" : ""}`}>{num(d.mean.wrongPer1000)}</td>
      <td className="tabular">{num(d.mean.costPer1000Eur, 2)}</td>
    </tr>
  );
}

function GateList({ title, gates, report }: { title: string; gates: Gate[]; report?: Report }) {
  const passed = gates.filter((g) => g.pass).length;
  return (
    <div className="gates">
      <h2>{title}</h2>
      <p className="section-sub">{passed} of {gates.length} pass{report ? `; ${report.questionsPerSeed} questions per seed` : ""}</p>
      <ul>
        {gates.map((g) => (
          <li key={g.id} className={g.pass ? "pass" : "fail"}>
            <span className="gate-mark" aria-label={g.pass ? "passes" : "fails"}>{g.pass ? "✓" : "✕"}</span>
            <span className="gate-label">{g.label}</span>
            <span className="gate-value tabular">{g.value == null ? "–" : +g.value.toFixed(4)} <span className="gate-limit">{g.limit}</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}
