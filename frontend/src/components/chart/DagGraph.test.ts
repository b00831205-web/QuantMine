import { describe, expect, it } from 'vitest';

import { layoutPositions } from './DagGraph';
import type { DagGraph } from '@/types/workflow';

const GRAPH: DagGraph = {
  nodes: [
    { id: 'universe_refresh', label: 'universe_refresh' },
    { id: 'data_downloading', label: 'data_downloading' },
    { id: 'data_cleaning', label: 'data_cleaning' },
  ],
  edges: [
    { source: 'universe_refresh', target: 'data_downloading' },
    { source: 'data_downloading', target: 'data_cleaning' },
  ],
};

describe('layoutPositions', () => {
  it('places every node and orders them left to right along the dependency chain', () => {
    const positions = layoutPositions(GRAPH);

    expect(Object.keys(positions).sort()).toEqual(
      ['data_cleaning', 'data_downloading', 'universe_refresh'],
    );
    expect(positions.universe_refresh!.x).toBeLessThan(positions.data_downloading!.x);
    expect(positions.data_downloading!.x).toBeLessThan(positions.data_cleaning!.x);
  });

  it('is deterministic for the same topology', () => {
    // The graph view re-renders on every poll tick. If the layout were not
    // reproducible, each tick would move the nodes while the ReactFlow viewport
    // stayed put -- which is how the graph ends up rendered outside the visible
    // area and looks like it vanished.
    expect(layoutPositions(GRAPH)).toEqual(layoutPositions(GRAPH));
  });

  it('does not depend on task state', () => {
    // Positions are a function of topology alone. This is what lets the node
    // memo key on a state *signature* instead of the state object, so a task
    // going from running to success recolours nodes without re-running dagre.
    const before = layoutPositions(GRAPH);
    const after = layoutPositions({ ...GRAPH, nodes: [...GRAPH.nodes] });
    expect(after).toEqual(before);
  });
});
