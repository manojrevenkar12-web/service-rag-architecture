import type { ReactNode } from "react";
import "./states.css";

export function Loading({ label }: { label: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="state-bar" aria-hidden />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="state state-error" role="alert">
      <p className="state-title">{title}</p>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="state state-empty">
      <p className="state-title">{title}</p>
      <p>{detail}</p>
    </div>
  );
}
