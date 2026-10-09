import { expect, test } from "vitest";
import { authorizationLabel, categoryLabel, severityLevel, timeAgo } from "./format";

test("severity levels", () => {
  expect([0, 2.9, 3, 4.9, 5, 6.9, 7, 8.9, 9, 10].map(severityLevel)).toEqual([
    "none", "none", "low", "low", "medium", "medium", "high", "high", "critical", "critical",
  ]);
});

test("labels fall back to the raw value", () => {
  expect(categoryLabel("data_exfiltration")).toBe("Data exfiltration");
  expect(categoryLabel("made_up")).toBe("made_up");
  expect(authorizationLabel("out_of_scope")).toBe("Out of scope");
});

test("timeAgo", () => {
  expect(timeAgo(null)).toBe("never");
  expect(timeAgo(100, 130)).toBe("30s ago");
  expect(timeAgo(0, 7200)).toBe("2h ago");
  expect(timeAgo(0, 3 * 86400)).toBe("3d ago");
});
