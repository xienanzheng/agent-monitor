import { screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { api } from "../api";
import { renderWith } from "../test/render";
import RulesPage from "./RulesPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, api: { ...actual.api, rules: vi.fn() } };
});

const mocked = vi.mocked(api);

test("an invalid rules file shows the validator's message", async () => {
  mocked.rules.mockResolvedValue({ rules: { error: "rule bad: category must be one of [...]" }, features: [] });
  renderWith(<RulesPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("rule bad: category must be one of");
});

test("rules are grouped by category", async () => {
  mocked.rules.mockResolvedValue({
    rules: [
      { type: "action", id: "alpha", category: "data_exfiltration", score: 4, pattern: "ALPHA_MARKER", kinds: [],
        tags_any: [], tags_all: [], add_tags: ["alpha_seen"], reason: "" },
      { type: "sequence", id: "seq", category: "data_exfiltration", score: 9, previous_tag: "alpha_seen",
        current_tag: "beta_seen", within_actions: 3, reason: "" },
    ],
    features: [{ tag: "example_marker", pattern: "ALPHA_MARKER", kinds: [], fields: ["text"] }],
  });
  renderWith(<RulesPage />);
  expect(await screen.findByRole("heading", { name: "Data exfiltration" })).toBeInTheDocument();
  expect(screen.getByText("alpha")).toBeInTheDocument();
  expect(screen.getByText(/alpha_seen → beta_seen within 3 actions/)).toBeInTheDocument();
  expect(screen.getByText("example_marker")).toBeInTheDocument();
});
