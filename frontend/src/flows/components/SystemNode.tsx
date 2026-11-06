import { Handle, Position, type NodeProps } from '@xyflow/react';
import { memo } from 'react';
import type { BandFlowNode, SystemFlowNode } from '../graphModel';
import { NODE_H, NODE_W } from '../layout';

const SIDES = [
  { side: 'left', position: Position.Left },
  { side: 'right', position: Position.Right },
  { side: 'top', position: Position.Top },
  { side: 'bottom', position: Position.Bottom },
] as const;
const SLOTS = { a: '35%', b: '65%' } as const;

const ROLE_LABEL = { upstream: 'Upstream', downstream: 'Downstream', focus: 'Exploring' } as const;

function SystemNodeView({ data }: NodeProps<SystemFlowNode>) {
  const { system, typeLabel, typeColor, dimmed, role, selected } = data;
  const emphasis = role === 'upstream' || role === 'downstream' || role === 'focus';
  return (
    <div
      className="system-node"
      style={{
        width: NODE_W,
        height: NODE_H,
        background: typeColor,
        opacity: dimmed ? 0.22 : 1,
        borderWidth: selected ? 3 : emphasis ? 2.5 : 1,
        borderStyle: system.type === 'queue_manager' ? 'dashed' : 'solid',
        borderColor: selected ? '#0f172a' : emphasis ? '#1e293b' : '#94a3b8',
      }}
      title={`${system.name} (${typeLabel})`}
    >
      {SIDES.flatMap(({ side, position }) =>
        (Object.keys(SLOTS) as (keyof typeof SLOTS)[]).flatMap((slot) => {
          const vertical = side === 'left' || side === 'right';
          const style = vertical ? { top: SLOTS[slot] } : { left: SLOTS[slot] };
          return [
            <Handle key={`s-${side}-${slot}`} id={`s-${side}-${slot}`} type="source" position={position} style={style} isConnectable={false} />,
            <Handle key={`t-${side}-${slot}`} id={`t-${side}-${slot}`} type="target" position={position} style={style} isConnectable={false} />,
          ];
        }),
      )}
      <div className="system-node__name">{system.name}</div>
      <div className="system-node__meta">
        <span>{typeLabel}</span>
        {role && <span className={`system-node__role system-node__role--${role}`}>{ROLE_LABEL[role]}</span>}
      </div>
    </div>
  );
}

function BandNodeView({ data }: NodeProps<BandFlowNode>) {
  return (
    <div className="layer-band">
      <div className="layer-band__label">{data.label}</div>
    </div>
  );
}

export const SystemNode = memo(SystemNodeView);
export const BandNode = memo(BandNodeView);
