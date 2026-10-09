import { expect, test } from "vitest";
import type { Overview } from "../api";
import { fullAccessShare, fullAccessText } from "./ExplorePage";

const base: Overview = { by_agent: {}, by_kind: {}, top_tools: [], top_shell_commands: [], policy: {} };

test("the full-access share counts only danger-full-access policy keys", () => {
  const o = { ...base, policy: { "never/danger-full-access": 3, "on-request/workspace-write": 1, "x/bypassPermissions": 4 } };
  expect(fullAccessShare(o)).toBeCloseTo(3 / 8);
  expect(fullAccessShare(base)).toBeNull();
});

test("the sentence names Codex actions, not turns", () => {
  const o = { ...base, policy: { "never/danger-full-access": 3, "on-request/workspace-write": 1 } };
  expect(fullAccessText(o)).toBe(
    "75% of Codex actions with a recorded sandbox policy ran with danger-full-access " +
      "(Claude Code permission modes are not recorded by ingest).",
  );
  expect(fullAccessText(base)).toBe("No sandbox policy recorded.");
});
