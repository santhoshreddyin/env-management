import { useState } from 'react';
import { envApi, type Variable } from '../api/env';

interface Props {
  envId: number;
  variable: Variable;
  onChange: () => Promise<void>;
  onError: (msg: string) => void;
}

export default function VariableRow({ envId, variable, onChange, onError }: Props) {
  const [editing, setEditing] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [value, setValue] = useState(variable.value);

  async function save() {
    try {
      await envApi.updateVariable(envId, variable.id, { value });
      setEditing(false);
      await onChange();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete ${variable.key}?`)) return;
    try {
      await envApi.deleteVariable(envId, variable.id);
      await onChange();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  const masked = variable.is_secret && !revealed;

  return (
    <tr>
      <td className="mono">{variable.key}</td>
      <td className="mono">
        {editing ? <input value={value} onChange={(e) => setValue(e.target.value)} autoFocus aria-label="Value" /> : masked ? '••••••••' : variable.value}
      </td>
      <td>
        {variable.is_secret && (
          <button className="link" onClick={() => setRevealed((r) => !r)}>
            {revealed ? 'Hide' : 'Show'}
          </button>
        )}
      </td>
      <td className="actions">
        {editing ? (
          <>
            <button onClick={save}>Save</button>
            <button
              className="secondary"
              onClick={() => {
                setValue(variable.value);
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            <button className="secondary" onClick={() => setEditing(true)}>
              Edit
            </button>
            <button className="danger" onClick={remove}>
              Delete
            </button>
          </>
        )}
      </td>
    </tr>
  );
}
