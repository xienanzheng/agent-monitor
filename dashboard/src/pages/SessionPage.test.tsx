import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { api } from "../api";
import { renderWith } from "../test/render";
import { eventRow } from "../test/rows";
import SessionPage from "./SessionPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, api: { ...actual.api, sessionActions: vi.fn() } };
});

const mocked = vi.mocked(api);

function page(route: string) {
  return renderWith(
    <Routes>
      <Route path="/sessions/:agent/:sessionId" element={<SessionPage source="live" />} />
    </Routes>,
    route,
  );
}

test("an action is selected by index and ts, so a reused index after a restart opens the right one", async () => {
  mocked.sessionActions.mockResolvedValue([
    eventRow({ index: 3, ts: 1000, text: "old action before restart" }),
    eventRow({ index: 3, ts: 2000, text: "new action after restart" }),
  ]);
  page("/sessions/claude_code/s1?action=3&ts=2000");
  const panel = await screen.findByTestId("action-panel");
  expect(panel).toHaveTextContent("new action after restart");
  expect(panel).not.toHaveTextContent("old action before restart");
});

test("timeline rows show their rule hits", async () => {
  mocked.sessionActions.mockResolvedValue([eventRow({ index: 0, text: "echo ALPHA_MARKER", rule_hits: ["example-marker"] })]);
  page("/sessions/claude_code/s1");
  const row = await screen.findByTestId("timeline-row");
  expect(row).toHaveTextContent("example-marker");
});
