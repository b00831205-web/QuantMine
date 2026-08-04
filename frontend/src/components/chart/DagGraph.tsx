import dagre from 'dagre';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import type { DagGraph, TaskInstance } from '@/types/workflow';

const NODE_WIDTH = 160;
const NODE_HEIGHT = 44;

const TASK_COLOR: Record<TaskInstance['status'], string> = {
  success: 'var(--positive)',
  failed: 'var(--negative)',
  running: 'var(--info)',
  skipped: 'var(--text-muted)',
  upstream_failed: 'var(--warning)',
};

/** 用 dagre 把 DAG 拓扑排版成从左到右的节点坐标（Airflow 同款思路） */
const layoutGraph = (
  graph: DagGraph,
  taskStatus?: Record<string, TaskInstance['status']>,
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
    const status = taskStatus?.[n.id];
    return {
      id: n.id,
      // dagre 返回的是节点中心坐标，ReactFlow 用的是左上角，所以要减去宽高的一半
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { label: n.label },
      ...(status
        ? { style: { background: TASK_COLOR[status], color: '#ffffff', border: 'none' } }
        : {}),
    };
  });

  const edges: Edge[] = graph.edges.map((e, i) => ({
    id: `${e.source}-${e.target}-${i}`,
    source: e.source,
    target: e.target,
    type: 'straight',
    sourcePosition: 'right',
    targetPosition: 'left',
  }));

  return { nodes, edges };
};

export const DagGraphView = ({
  graph,
  taskStatus,
}: {
  graph: DagGraph;
  taskStatus?: Record<string, TaskInstance['status']>;
}) => {
  const { nodes, edges } = layoutGraph(graph, taskStatus);

  return (
    <div
      style={{
        height: 420,
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
