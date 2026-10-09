import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { api } from "../api";
import { eventRow } from "../test/rows";
import { useLiveFeed } from "./useLiveFeed";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, api: { ...actual.api, eventsTail: vi.fn(), eventsAfter: vi.fn() } };
});

const mocked = vi.mocked(api);

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

test("the cursor carries file_id, and a reset re-tails and replaces the rows", async () => {
  vi.useFakeTimers();
  mocked.eventsTail
    .mockResolvedValueOnce({ rows: [eventRow({ index: 0, text: "old file" })], next: 10, reset: false, file_id: 1 })
    .mockResolvedValueOnce({ rows: [eventRow({ index: 0, scored_ts: 5, text: "new file" })], next: 4, reset: false, file_id: 2 });
  mocked.eventsAfter.mockResolvedValueOnce({ rows: [], next: 0, reset: true, file_id: 2 });

  const { result, unmount } = renderHook(() => useLiveFeed("live", 1000));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(result.current.rows.map((r) => r.text)).toEqual(["old file"]);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(mocked.eventsAfter).toHaveBeenCalledWith("live", 10, 1);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(mocked.eventsTail).toHaveBeenCalledTimes(2);
  expect(result.current.rows.map((r) => r.text)).toEqual(["new file"]);
  unmount();
});
