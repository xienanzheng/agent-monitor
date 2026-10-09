import { screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { api } from "../api";
import { renderWith } from "../test/render";
import EvaluationPage from "./EvaluationPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, api: { ...actual.api, evalResults: vi.fn(), labelledFiles: vi.fn() } };
});

const mocked = vi.mocked(api);

test("not run yet shows the run form", async () => {
  mocked.evalResults.mockResolvedValue({ missing: true });
  mocked.labelledFiles.mockResolvedValue(["tests/fixtures/labelled_sample.jsonl"]);
  renderWith(<EvaluationPage />);
  expect(await screen.findByText(/No eval results yet/)).toBeInTheDocument();
  expect(await screen.findByRole("option", { name: "tests/fixtures/labelled_sample.jsonl" })).toBeInTheDocument();
});

test("a scorer row shows AUC, catch rates and judge failures", async () => {
  mocked.evalResults.mockResolvedValue({
    split: "dev",
    scorers: {
      rules: {
        auc: 0.75,
        tpr_at_fpr: { "0.01": 0.5, "0.05": 0.6 },
        threshold_at_5pct: 4,
        test_confusion: { tp: 1, fp: 0, tn: 2, fn: 1 },
        n_test: 4,
        median_latency_ms: 0.01,
        judge_calls: 10,
        judge_failures: 2,
      },
    },
  });
  mocked.labelledFiles.mockResolvedValue([]);
  renderWith(<EvaluationPage />);
  const row = await screen.findByRole("row", { name: /rules/ });
  expect(row).toHaveTextContent("0.750");
  expect(row).toHaveTextContent("50%");
  expect(row).toHaveTextContent("60%");
  expect(row).toHaveTextContent("2 / 10");
});

test("legacy results disclose unknown provenance", async () => {
  mocked.evalResults.mockResolvedValue({ split: "test", scorers: {} });
  mocked.labelledFiles.mockResolvedValue([]);
  renderWith(<EvaluationPage />);
  expect(await screen.findByText(/Legacy measurements/)).toHaveTextContent("unknown provenance");
});

test('legacy scorer measurements are not presented as a verified model comparison', async () => {
  const row={auc:.5,tpr_at_fpr:{'0.01':0,'0.05':0},threshold_at_5pct:5,test_confusion:null,n_test:2,median_latency_ms:1};
  mocked.evalResults.mockResolvedValue({split:'unknown',scorers:{rules:row,judge:row}});
  mocked.labelledFiles.mockResolvedValue([]);
  renderWith(<EvaluationPage/>);
  await screen.findByText(/Legacy measurements/);
  expect(screen.queryByRole('region',{name:'Scorer comparison, scroll for more columns'})).not.toBeInTheDocument();
});

test('separates final judge failures from actual inference requests and retries', async () => {
  mocked.evalResults.mockResolvedValue({schema_version:2,split:'test',provenance:{created_at:'2026-10-09',dataset:'synthetic.jsonl',dataset_kind:'original_synthetic',hashes:{},models:['local'],threshold_source:'dev',dev_trajectories:2,test_trajectories:2},scorers:{judge:{auc:.5,tpr_at_fpr:{'0.01':0,'0.05':0},threshold_at_5pct:5,test_confusion:null,n_test:2,median_latency_ms:1,judge_calls:2,judge_failures:0,inference_requests:3,inference_retries:1}}});
  mocked.labelledFiles.mockResolvedValue([]);
  renderWith(<EvaluationPage/>);
  const row=await screen.findByRole('row',{name:/judge/});
  expect(row).toHaveTextContent('0 / 2');
  expect(row).toHaveTextContent('3 requests · 1 retry');
});
