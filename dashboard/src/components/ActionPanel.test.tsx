import { fireEvent, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { renderWith } from "../test/render";
import { eventRow, verdict } from "../test/rows";
import ActionPanel from "./ActionPanel";

test("shows the rescored row and the judge-failed note", () => {
  const main = eventRow({
    index: 2,
    text: "echo ALPHA_MARKER",
    settled_by: "triage",
    judge_failed: true,
    triage: verdict({ score: 4 }),
    final_severity: 4,
  });
  const post = eventRow({ index: 2, settled_by: "rules_post", final_severity: 6, tags: ["secret_in_output"], rule_hits: ["leak"] });
  renderWith(<ActionPanel rows={[main, post]} source="live" onClose={() => {}} />);
  const panel = screen.getByTestId("action-panel");
  expect(panel).toHaveTextContent("echo ALPHA_MARKER");
  expect(panel).toHaveTextContent("a judge failed");
  expect(panel).toHaveTextContent("Rescored after its output");
  expect(panel).toHaveTextContent("leak");
});

test("close calls back", () => {
  const onClose = vi.fn();
  renderWith(<ActionPanel rows={[eventRow()]} source="live" onClose={onClose} />);
  fireEvent.click(screen.getByLabelText("close"));
  expect(onClose).toHaveBeenCalled();
});

test("rule reasons and the rescored reason are shown when no judge gave one", () => {
  const main = eventRow({ index: 2, settled_by: "rules_high", final_severity: 9, rule_hits: ["alpha"], reason: "ALPHA rule fired" });
  const post = eventRow({ index: 2, settled_by: "rules_post", final_severity: 9.5, rule_hits: ["leak"], reason: "secret in output" });
  renderWith(<ActionPanel rows={[main, post]} source="live" onClose={() => {}} />);
  const panel = screen.getByTestId("action-panel");
  expect(panel).toHaveTextContent("Rule reasons: ALPHA rule fired");
  expect(panel).toHaveTextContent("secret in output");
});

test("links the incident even when only the rescored row opened it", () => {
  const main = eventRow({ index: 2, final_severity: 4, incident_id: null });
  const post = eventRow({ index: 2, settled_by: "rules_post", final_severity: 6, incident_id: "inc-9" });
  renderWith(<ActionPanel rows={[main, post]} source="live" onClose={() => {}} />);
  expect(screen.getByRole("link", { name: "Incident inc-9" })).toBeInTheDocument();
});

test("latest output without a score increase is visible and Escape restores focus", () => {
  const onClose = vi.fn();
  const trigger = document.createElement("button");
  document.body.append(trigger);
  trigger.focus();
  const view = renderWith(<ActionPanel rows={[eventRow(), eventRow({ settled_by: "output_update", output: "Finished safely" })]} source="live" onClose={onClose} />);
  expect(screen.getByRole("dialog")).toHaveTextContent("Finished safely");
  expect(screen.getByLabelText("close")).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(onClose).toHaveBeenCalled();
  view.unmount();
  expect(trigger).toHaveFocus();
  trigger.remove();
});

test('rule explanations remain separate when the model also gives a reason', () => {
  renderWith(<ActionPanel rows={[eventRow({triage:verdict(),rule_reasons:['Matched upload source path']})]} source="live" onClose={() => {}}/>);
  expect(screen.getByTestId('action-panel')).toHaveTextContent('Matched upload source path');
});

test('slow inference is pending without claiming a failed judge', () => {
  renderWith(<ActionPanel rows={[eventRow({settled_by:'output_update',assessment_state:'pending',judge_failed:false,triage:null,gateway:null})]} source="live" onClose={() => {}}/>);
  expect(screen.getByTestId('action-panel')).toHaveTextContent('Assessment pending');
  expect(screen.getByTestId('action-panel')).not.toHaveTextContent('a judge failed');
});

test('a completed asynchronous judgment replaces pending routing and explanation', () => {
  const pending = eventRow({ settled_by:'pending', assessment_state:'pending', triage:null, reason:'Queued for review' });
  const completed = eventRow({ settled_by:'triage', assessment_state:'assessed', triage:verdict({reason:'Authorized public report'}), reason:'Authorized public report' });
  const output = eventRow({ settled_by:'output_update', assessment_state:'assessed', triage:null, output:'Uploaded report', reason:'' });
  renderWith(<ActionPanel rows={[pending, completed, output]} source="live" onClose={() => {}}/>);
  const panel=screen.getByTestId('action-panel');
  expect(panel).toHaveTextContent('Settled by triage');
  expect(panel).toHaveTextContent('Authorized public report');
  expect(panel).toHaveTextContent('Uploaded report');
  expect(panel).not.toHaveTextContent('Queued for review');
});
