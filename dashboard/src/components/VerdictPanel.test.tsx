import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { verdict } from "../test/rows";
import VerdictPanel, { reasoningSteps } from "./VerdictPanel";

test("splits numbered reasoning into steps", () => {
  expect(reasoningSteps("1. First step. 2. Second, with 3 items. 3. Third")).toEqual([
    "First step.",
    "Second, with 3 items.",
    "Third",
  ]);
  expect(reasoningSteps("")).toEqual([]);
  expect(reasoningSteps("no numbers here")).toEqual(["no numbers here"]);
});

test("renders the gateway verdict with labels and steps", () => {
  render(<VerdictPanel title="Gateway" verdict={verdict()} testId="verdict-gateway" />);
  const panel = screen.getByTestId("verdict-gateway");
  expect(panel).toHaveTextContent("Out of scope");
  expect(panel).toHaveTextContent("Data exfiltration");
  expect(panel).toHaveTextContent("80%");
  expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "The user asked to run the tests.",
    "It prints a credential.",
  ]);
});

test("a failed judge says so", () => {
  render(<VerdictPanel title="Triage" verdict={verdict({ failed: true, score: null, reason: "judge error: timed out" })} testId="t" />);
  expect(screen.getByTestId("t")).toHaveTextContent("Judge failed: judge error: timed out");
});

test("a judge that never ran says so", () => {
  render(<VerdictPanel title="Triage" verdict={null} testId="t" />);
  expect(screen.getByTestId("t")).toHaveTextContent("Not run for this action.");
});

test("shows failure cause and elapsed inference time", () => {
  render(<VerdictPanel title="Triage" verdict={verdict({failed:true,score:null,error_code:"timeout",model:"qwen3:4b",latency_s:90,reason:"judge error: timed out"})} testId="t" />);
  expect(screen.getByTestId("t")).toHaveTextContent("qwen3:4b · 90.0 s");
  expect(screen.getByTestId("t")).toHaveTextContent("Inference timed out");
});

test("shows server timing separately from total request latency", () => {
  render(<VerdictPanel title="Gateway" verdict={verdict({timing:{load_s:2,prompt_s:1,generation_s:3,output_tokens:60}})} testId="t" />);
  expect(screen.getByTestId("t")).toHaveTextContent("Load 2.0 s");
  expect(screen.getByTestId("t")).toHaveTextContent("Generate 3.0 s");
});

test("shows recovered server errors without calling the final verdict failed", () => {
  render(<VerdictPanel title="Gateway" verdict={verdict({request_attempts:2,retry_errors:[{error_code:"http_error",http_status:500,elapsed_s:5.5}]})} testId="t" />);
  expect(screen.getByTestId("t")).toHaveTextContent("Completed after 2 requests");
  expect(screen.getByTestId("t")).toHaveTextContent("HTTP 500");
  expect(screen.getByTestId("t")).not.toHaveTextContent("Judge failed");
});
