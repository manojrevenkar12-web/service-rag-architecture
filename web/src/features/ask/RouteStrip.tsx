import { motion, useReducedMotion } from "framer-motion";
import type { Stage } from "./api";
import "./route.css";

/** The agent graph as a terminal strip: each node a block, the path the request took lit up in order. */
export function RouteStrip({ stages, runKey }: { stages: Stage[]; runKey: string }) {
  const still = useReducedMotion();
  const taken = stages.filter((s) => s.visits > 0);
  return (
    <ol className="route" aria-label="What the assistant did">
      {stages.map((s) => {
        const order = taken.indexOf(s);
        const on = s.visits > 0;
        return (
          <motion.li
            key={`${runKey}-${s.id}`}
            className={`terminal ${on ? "on" : "off"} ${s.failed ? "failed" : ""}`}
            initial={still ? false : { opacity: 0.35 }}
            animate={{ opacity: on ? 1 : 0.45 }}
            transition={{ delay: still ? 0 : Math.max(order, 0) * 0.12, duration: 0.25 }}
          >
            <span className="terminal-head">
              <span className="terminal-name">{s.label}</span>
              {s.visits > 1 && <span className="terminal-count tabular">×{s.visits}</span>}
            </span>
            <span className="terminal-notes">
              {on ? s.notes.map((n, i) => <span key={i}>{n}</span>) : <span>skipped</span>}
            </span>
          </motion.li>
        );
      })}
    </ol>
  );
}
