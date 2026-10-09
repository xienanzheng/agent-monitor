import { screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { api } from '../api';
import { renderWith } from '../test/render';
import AnalysisStrip from './AnalysisStrip';
vi.mock('../api', async (original) => {
  const actual=await original<typeof import('../api')>();
  return {...actual,api:{...actual.api,analysis:vi.fn()}};
});
test('distinguishes failed stages from recovered and incomplete actions', async () => {
  vi.mocked(api.analysis).mockResolvedValue({source:'live',window:{hours:24,end_ts:200},actions:2,flagged:1,incomplete:1,assessed:1,threshold:5,unknown_tools:0,categories:{},judging:{actions:2,median_latency_s:22,stage_attempts:3,failures:{timeout:2},recovered_actions:1}});
  renderWith(<AnalysisStrip source="live"/>);
  expect(await screen.findByText(/2 failed stage calls/)).toHaveTextContent('3 stage calls');
  expect(screen.getByText(/Recovered by fallback/)).toHaveTextContent('1 action');
});

test('shows retried model requests separately from completed stages', async () => {
  vi.mocked(api.analysis).mockResolvedValue({source:'live',window:{hours:24,end_ts:200},actions:1,flagged:0,incomplete:0,assessed:1,threshold:5,unknown_tools:0,categories:{},judging:{actions:1,median_latency_s:8,stage_attempts:1,failures:{},request_attempts:2,retried_actions:1}});
  renderWith(<AnalysisStrip source="live"/>);
  expect(await screen.findByText(/Server retries/)).toHaveTextContent('1 action');
  expect(screen.getByText(/Server retries/)).toHaveTextContent('2 requests');
});
