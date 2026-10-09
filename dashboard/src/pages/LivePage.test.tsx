import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "../api";
import { renderWith } from "../test/render";
import { eventRow } from "../test/rows";
import LivePage from "./LivePage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, api: { ...actual.api, incidents: vi.fn(), eventsTail: vi.fn(), eventsAfter: vi.fn() } };
});

const mocked = vi.mocked(api);

beforeEach(() => {
  mocked.incidents.mockResolvedValue([]);
  mocked.eventsTail.mockResolvedValue({ rows: [], next: 0, reset: false, file_id: null });
  mocked.eventsAfter.mockResolvedValue({ rows: [], next: 0, reset: false, file_id: null });
});

test("empty logs show empty states, not errors", async () => {
  renderWith(<LivePage source="live" />);
  expect(await screen.findByText("No incidents.")).toBeInTheDocument();
  expect(screen.getByText("No events yet.")).toBeInTheDocument();
  expect(mocked.incidents).toHaveBeenCalledWith("live", 24);
});

test("the severity filter hides low rows", async () => {
  mocked.eventsTail.mockResolvedValue({
    rows: [
      eventRow({ index: 0, text: "pytest -q", final_severity: 1 }),
      eventRow({ index: 1, text: "echo ALPHA_MARKER", final_severity: 7 }),
    ],
    next: 10,
    reset: false,
    file_id: null,
  });
  renderWith(<LivePage source="live" />);
  expect(await screen.findByText("echo ALPHA_MARKER")).toBeInTheDocument();
  expect(screen.getByText("pytest -q")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText(/severity ≥ 5 only/));
  expect(screen.queryByText("pytest -q")).not.toBeInTheDocument();
  expect(screen.getByText("echo ALPHA_MARKER")).toBeInTheDocument();
});

test("replay shows every incident, whatever its age", async () => {
  renderWith(<LivePage source="replay" />);
  await screen.findByText("No incidents.");
  expect(mocked.incidents).toHaveBeenCalledWith("replay", undefined);
});
