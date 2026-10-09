import { screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { renderWith } from '../test/render';
import { eventRow } from '../test/rows';
import FeedRow from './FeedRow';

test('a low retained severity still shows an incomplete assessment in the stream', () => {
  renderWith(<FeedRow row={eventRow({judge_failed:true,final_severity:2})} source="live" now={0}/>);
  expect(screen.getByTestId('feed-row')).toHaveTextContent('Incomplete');
});

test('waiting for slow inference is labelled pending', () => {
  renderWith(<FeedRow row={eventRow({assessment_state:'pending',judge_failed:false,final_severity:2})} source="live" now={0}/>);
  expect(screen.getByTestId('feed-row')).toHaveTextContent('Pending');
  expect(screen.getByTestId('feed-row')).not.toHaveTextContent('Incomplete');
});
