import dagre from 'dagre';
import ReactFlow, { Background, Controls, Position, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import type { DagGraph } from '@/types/workflow';
import { stateColor } from '@/utils/workflowStatus';

const NODE_WIDTH = 170;
const NODE_HEIGHT = 44;

/** 用 dagre 把 DAG 拓扑排版成从左到右的节点坐标（Airflow 同款思路） */
const layoutGraph = (
  graph: DagGraph,
  taskStates?: Record<string, string | null>,
): { nodes: Node[]; edges: Edge[] } => {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 80 });

  for (const n of graph.nodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT, label: n.label });
  }
  for (const e of graph.edges) {
    g.setEdge(e.source, e.target);
  }

  dagre.layout(g);

  const nodes: Node[] = graph.nodes.map((n) => {
    const pos = g.node(n.id);
    const state = taskStates?.[n.id] ?? null;
    const color = stateColor(state);
    return {
      id: n.id,
      // dagre 返回的是节点中心坐标，ReactFlow 用左上角，故减去半宽高
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { label: n.label },
      // 句柄放在左右两侧，边才会水平相接（否则默认在上/下，连线会从底部绕出）
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        background: 'var(--bg-surface)',
        color: 'var(--text-primary)',
        border: `2px solid ${color}`,
        borderLeft: `8px solid ${color}`,
        borderRadius: 8,
        width: NODE_WIDTH,
        fontSize: 12,
      },
    };
  });

  const edges: Edge[] = graph.edges.map((e, i) => ({
    id: `${e.source}-${e.target}-${i}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    animated: taskStates?.[e.source] === 'running',
  }));

  return { nodes, edges };
};

export const DagGraphView = ({
  graph,
  taskStates,
  height = 420,
}: {
  graph: DagGraph;
  taskStates?: Record<string, string | null>;
  height?: number;
}) => {
  const { nodes, edges } = layoutGraph(graph, taskStates);

  return (
    <div
      style={{
        height,
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-surface-2)',
      }}
    >
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background gap={16} />
        <Controls />
      </ReactFlow>
    </div>
  );
};
