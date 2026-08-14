import { useMemo } from 'react';
import dagre from 'dagre';
import ReactFlow, { Background, Controls, Position, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import type { DagGraph } from '@/types/workflow';
import { stateColor } from '@/utils/workflowStatus';

const NODE_WIDTH = 170;
const NODE_HEIGHT = 44;

/** 用 dagre 把 DAG 拓扑排版成从左到右的节点坐标（Airflow 同款思路）。
 *
 * 只吃拓扑，不吃任务状态。坐标与状态分开算是有意为之：状态每几秒变一次，
 * 拓扑在一个页面的生命周期里根本不变，混在一起会让一个任务从 running 变
 * success 就重排整张图。 */
export const layoutPositions = (graph: DagGraph): Record<string, { x: number; y: number }> => {
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

  const positions: Record<string, { x: number; y: number }> = {};
  for (const n of graph.nodes) {
    const pos = g.node(n.id);
    // dagre 返回的是节点中心坐标，ReactFlow 用左上角，故减去半宽高
    positions[n.id] = { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 };
  }
  return positions;
};

/** 任务状态的稳定签名。
 *
 * 轮询每轮都把整个 grid 响应换掉，于是 ``taskStates`` 即使一个值都没变也是
 * 新对象。直接拿它当 memo 依赖等于没有 memo，所以这里比较内容而不是身份。 */
const statesSignature = (
  graph: DagGraph,
  taskStates?: Record<string, string | null>,
): string => graph.nodes.map((n) => `${n.id}:${taskStates?.[n.id] ?? ''}`).join('|');

export const DagGraphView = ({
  graph,
  taskStates,
  height = 420,
}: {
  graph: DagGraph;
  taskStates?: Record<string, string | null>;
  height?: number;
}) => {
  const positions = useMemo(() => layoutPositions(graph), [graph]);
  const signature = statesSignature(graph, taskStates);

  // 依赖里是 signature 而不是 taskStates：后者每轮轮询都是新对象身份，进了依赖
  // 就等于每 5 秒重建一次 nodes/edges。ReactFlow 在受控模式下拿到新数组会重置
  // 节点已测量的尺寸，而 fitView 只在首次渲染适配一次，不会再适配——重置后视口
  // 仍是旧的，图就可能整片落到可视区外，看起来像消失了。
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const nodes = useMemo<Node[]>(
    () =>
      graph.nodes.map((n) => {
        const color = stateColor(taskStates?.[n.id] ?? null);
        return {
          id: n.id,
          position: positions[n.id] ?? { x: 0, y: 0 },
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
      }),
    [graph, positions, signature],
  );

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const edges = useMemo<Edge[]>(
    () =>
      graph.edges.map((e, i) => ({
        id: `${e.source}-${e.target}-${i}`,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
        animated: taskStates?.[e.source] === 'running',
      })),
    [graph, signature],
  );

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
