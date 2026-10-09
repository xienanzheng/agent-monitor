import { expect, test } from "vitest";
import { mergeFeed } from "./feed";
import { eventRow } from "./test/rows";

const a = eventRow({ index: 0, scored_ts: 1 });
const b = eventRow({ index: 1, scored_ts: 2 });
const c = eventRow({ index: 2, scored_ts: 3 });

test("new rows go on top, newest first", () => {
  expect(mergeFeed([], [a, b], false).map((r) => r.index)).toEqual([1, 0]);
  expect(mergeFeed([b, a], [c], false).map((r) => r.index)).toEqual([2, 1, 0]);
});

test("rows already shown are not duplicated", () => {
  expect(mergeFeed([a], [a], false)).toHaveLength(1);
});

test("reset drops what was shown", () => {
  expect(mergeFeed([a], [b], true).map((r) => r.index)).toEqual([1]);
});

test("the feed is capped", () => {
  const many = Array.from({ length: 5 }, (_, i) => eventRow({ index: i, scored_ts: i }));
  expect(mergeFeed([], many, false, 3).map((r) => r.index)).toEqual([4, 3, 2]);
});

test("output revisions update one action and preserve earlier model evidence", () => {
  const original = eventRow({ action_id: "one", final_severity: 7, gateway: { score: 7 } as never });
  const output = eventRow({ action_id: "one", settled_by: "output_update", scored_ts: 5, final_severity: 3, output: "done", gateway: null });
  const rows = mergeFeed([original], [output], false);
  expect(rows).toHaveLength(1);
  expect(rows[0].output).toBe("done");
  expect(rows[0].final_severity).toBe(7);
  expect(rows[0].gateway?.score).toBe(7);
});
