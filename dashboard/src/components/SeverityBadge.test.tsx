import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import SeverityBadge from "./SeverityBadge";

test("shows the real score with its level class", () => {
  render(<SeverityBadge score={7.4} />);
  expect(screen.getByText("7.4")).toHaveClass("sev", "sev-high");
});

test("a fractional score just below a band keeps label, colour and filter consistent", () => {
  render(<SeverityBadge score={4.6} />);
  expect(screen.getByText("4.6")).toHaveClass("sev-low");
});

test("a whole score has no decimal", () => {
  render(<SeverityBadge score={7} />);
  expect(screen.getByText("7")).toHaveClass("sev-high");
});

test("an unscored action shows a dash", () => {
  render(<SeverityBadge score={null} />);
  expect(screen.getByText("–")).toHaveClass("sev-unknown");
});
