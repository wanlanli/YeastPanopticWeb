import { hierarchy, scaleLinear, stratify, tree } from 'd3';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import type { TrackingNode } from '../../api/types';
import { CATEGORICAL, INK } from './palette';
import './TrackingTree.css';

interface Props {
  datasetId: number;
}

const VIRTUAL_ROOT = '__virtual_root__';
const ROW_HEIGHT = 22;
const COL_WIDTH = 140;
const MARGIN = { top: 20, right: 40, bottom: 20, left: 40 };

export function TrackingTree({ datasetId }: Props) {
  const [nodes, setNodes] = useState<TrackingNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getTracking(datasetId)
      .then((res) => setNodes(res.nodes))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [datasetId]);

  const layout = useMemo(() => {
    if (nodes.length === 0) return null;

    const withVirtualRoot = [
      { id: VIRTUAL_ROOT, parent_id: null } as TrackingNode,
      ...nodes,
    ];
    let root;
    try {
      root = stratify<TrackingNode>()
        .id((d) => String(d.id))
        .parentId((d) => (d.id === VIRTUAL_ROOT ? null : d.parent_id == null ? VIRTUAL_ROOT : String(d.parent_id)))(
        withVirtualRoot,
      );
    } catch {
      // Fall back to a flat forest wrapped under the virtual root if ids are inconsistent
      root = hierarchy({ id: VIRTUAL_ROOT, parent_id: null, children: [] } as TrackingNode);
    }

    const layoutFn = tree<TrackingNode>().nodeSize([ROW_HEIGHT, COL_WIDTH]);
    layoutFn(root);

    const allNodes = root.descendants().filter((d) => d.data.id !== VIRTUAL_ROOT);
    const allLinks = root
      .links()
      .filter((l) => l.source.data.id !== VIRTUAL_ROOT || l.target.data.id !== VIRTUAL_ROOT);

    const hasFrameInfo = nodes.some((n) => typeof n.frame_start === 'number');
    let xForDepth = (d: (typeof allNodes)[number]) => d.y ?? 0;
    if (hasFrameInfo) {
      const frames = nodes
        .map((n) => n.frame_start)
        .filter((v): v is number => typeof v === 'number');
      const scale = scaleLinear()
        .domain([Math.min(...frames), Math.max(...frames)])
        .range([0, Math.max(1, allNodes.length) * 30]);
      xForDepth = (d) =>
        typeof d.data.frame_start === 'number' ? scale(d.data.frame_start) : (d.y ?? 0);
    }

    const minX = Math.min(0, ...allNodes.map((d) => d.x ?? 0));
    const maxX = Math.max(0, ...allNodes.map((d) => d.x ?? 0));
    const maxY = Math.max(0, ...allNodes.map((d) => xForDepth(d)));

    return {
      nodes: allNodes.map((d) => ({
        id: String(d.data.id),
        data: d.data,
        screenX: xForDepth(d) + MARGIN.left,
        screenY: (d.x ?? 0) - minX + MARGIN.top,
      })),
      links: allLinks
        .filter((l) => l.source.data.id !== VIRTUAL_ROOT)
        .map((l) => ({
          id: `${l.source.data.id}->${l.target.data.id}`,
          x1: xForDepth(l.source) + MARGIN.left,
          y1: (l.source.x ?? 0) - minX + MARGIN.top,
          x2: xForDepth(l.target) + MARGIN.left,
          y2: (l.target.x ?? 0) - minX + MARGIN.top,
        })),
      width: maxY + MARGIN.left + MARGIN.right,
      height: maxX - minX + MARGIN.top + MARGIN.bottom,
    };
  }, [nodes]);

  const hoveredNode = layout?.nodes.find((n) => n.id === hoverId);

  return (
    <div className="tracking-tree-panel">
      <div className="tracking-tree-header">
        {loading && <span className="tracking-tree-loading">loading…</span>}
        {error && <span className="tracking-tree-error">{error}</span>}
        {!loading && !error && nodes.length === 0 && (
          <span className="tracking-tree-loading">No tracking data.</span>
        )}
      </div>

      <div className="tracking-tree-scroll">
        {layout && (
          <svg width={layout.width} height={layout.height}>
            {layout.links.map((l) => (
              <path
                key={l.id}
                d={`M${l.x1},${l.y1} C${(l.x1 + l.x2) / 2},${l.y1} ${(l.x1 + l.x2) / 2},${l.y2} ${l.x2},${l.y2}`}
                fill="none"
                stroke={INK.gridline}
                strokeWidth={1.5}
              />
            ))}
            {layout.nodes.map((n) => (
              <g
                key={n.id}
                transform={`translate(${n.screenX},${n.screenY})`}
                onMouseEnter={() => setHoverId(n.id)}
                onMouseLeave={() => setHoverId((cur) => (cur === n.id ? null : cur))}
              >
                <circle r={hoverId === n.id ? 6 : 4.5} fill={CATEGORICAL[0]} />
                <text x={8} y={4} fontSize={11} fill={INK.secondary}>
                  {String(n.data.label ?? n.id)}
                </text>
              </g>
            ))}
          </svg>
        )}
      </div>

      {hoveredNode && (
        <div className="tracking-tree-tooltip">
          {Object.entries(hoveredNode.data)
            .filter(([k]) => k !== 'children')
            .map(([k, v]) => (
              <div key={k}>
                <strong>{k}:</strong> {String(v)}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
