import { BaseEdge, EdgeLabelRenderer, Position, getBezierPath, type EdgeProps } from '@xyflow/react';
import { memo } from 'react';
import type { FlowEdge } from '../graphModel';

/**
 * Edge of the selected path. Labels of request edges sit slightly above the curve's
 * midpoint and reply labels slightly below, so a request/reply pair between the same
 * systems never overlaps.
 */
function PathEdgeView(props: EdgeProps<FlowEdge>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, label, data, selected } = props;
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  const reply = data?.direction === 'reply';
  const color = (style?.stroke as string) ?? '#334155';
  // Vertical edges (same layer): put labels beside the line; otherwise above/below it.
  const vertical = sourcePosition === Position.Top || sourcePosition === Position.Bottom;
  const offset = vertical
    ? `translate(${reply ? '8px' : 'calc(-100% - 8px)'}, -50%)`
    : `translate(-50%, calc(-50% + ${reply ? 11 : -11}px))`;
  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} interactionWidth={16} />
      {label && (
        <EdgeLabelRenderer>
          <div
            className="path-edge-label nodrag nopan"
            style={{
              transform: `translate(${labelX}px, ${labelY}px) ${offset}`,
              zIndex: 1000,
              color,
              borderColor: color,
              borderStyle: reply ? 'dashed' : 'solid',
              borderWidth: selected ? 2 : 1,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const PathEdge = memo(PathEdgeView);
