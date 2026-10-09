import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useNow } from "./useNow";

afterEach(() => vi.useRealTimers());

test("useNow keeps ticking so relative times age", () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useNow(1000));
  const start = result.current;
  act(() => {
    vi.advanceTimersByTime(3000);
  });
  expect(result.current - start).toBeCloseTo(3, 0);
});
