import { describe, expect, it } from 'vitest';

import { STATE_COLOR, STATE_LABEL, TERMINAL_STATES, isActiveState } from './workflowStatus';

/**
 * Every state the app knows about, taken from the `AirflowState` union. Listed
 * literally rather than derived so that adding a state to the union without
 * deciding whether it is terminal fails here instead of silently defaulting to
 * "still running" and polling forever.
 */
const ALL_STATES = [
  'success',
  'failed',
  'running',
  'queued',
  'scheduled',
  'skipped',
  'upstream_failed',
  'up_for_retry',
  'up_for_reschedule',
  'deferred',
  'removed',
  'restarting',
  'none',
] as const;

describe('isActiveState', () => {
  it.each([
    ['running', true],
    ['queued', true],
    ['scheduled', true],
    ['restarting', true],
    // The ones a hand-written "active" list forgets. A task sitting out its
    // retry backoff is alive and will change on its own; treating it as
    // finished freezes the view at the exact moment it looks broken.
    ['up_for_retry', true],
    ['up_for_reschedule', true],
    ['deferred', true],
    ['success', false],
    ['failed', false],
    ['skipped', false],
    ['upstream_failed', false],
    ['removed', false],
    // No state is not evidence of work in progress; letting it count would keep
    // an idle page polling at the fast interval.
    ['none', false],
  ])('classifies %s as active=%s', (state, expected) => {
    expect(isActiveState(state)).toBe(expected);
  });

  it('treats null and undefined as inactive', () => {
    expect(isActiveState(null)).toBe(false);
    expect(isActiveState(undefined)).toBe(false);
  });

  it('covers every state the rest of the UI can render', () => {
    // Guards against the classifier drifting from the palette/labels: anything
    // with a colour and a label is something a user can see, so it needs a
    // deliberate active/terminal answer.
    for (const state of ALL_STATES) {
      expect(STATE_COLOR).toHaveProperty(state);
      expect(STATE_LABEL).toHaveProperty(state);
      expect(typeof isActiveState(state)).toBe('boolean');
    }
    const classified = ALL_STATES.filter((s) => TERMINAL_STATES.has(s) || isActiveState(s));
    expect(classified).toHaveLength(ALL_STATES.length);
  });
});
