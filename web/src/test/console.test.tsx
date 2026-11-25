import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../app/App";
import { route } from "../features/ask/api";

afterEach(() => vi.restoreAllMocks());

describe("route", () => {
  it("maps the agent's step log onto the strip, counting retries and failed checks", () => {
    const stages = route(["guard", "understand", "registry 6VD1234-5AB0 -> VD-340", "retrieve 5", "read", "verify: quoted line does not name VD-340", "read", "verify: ok", "respond"]);
    const by = Object.fromEntries(stages.map((s) => [s.id, s]));
    expect(by.read.visits).toBe(2);
    expect(by.verify.failed).toBe(true);
    expect(by.understand.notes[0]).toContain("VD-340");
    expect(by.tools.visits).toBe(0);
  });
});

describe("console states", () => {
  it("says how to start the service when it is not reachable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    render(<App initial="ask" />);
    expect(await screen.findByText(/Start it with `sra serve`/)).toBeInTheDocument();
    expect(screen.getByText("No question yet")).toBeInTheDocument();
  });

  it("says how to generate study results when they are missing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 404 }));
    render(<App initial="study" />);
    expect(await screen.findByText(/Run `sra lab dev`/)).toBeInTheDocument();
  });
});
