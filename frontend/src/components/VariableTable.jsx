import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client.js';
import VariableRow from './VariableRow.jsx';

const EMPTY = { key: '', value: '', is_secret: false };

export default function VariableTable({ environment, onChange, onError }) {
  const [variables, setVariables] = useState([]);
  const [draft, setDraft] = useState(EMPTY);

  const load = useCallback(async () => {
    try {
      setVariables(await api.listVariables(environment.id));
    } catch (err) {
      onError(err.message);
    }
  }, [environment.id, onError]);

  useEffect(() => {
    load();
  }, [load]);

  async function refresh() {
    await load();
    await onChange();
  }

  async function handleAdd(e) {
    e.preventDefault();
    try {
      await api.createVariable(environment.id, draft);
      setDraft(EMPTY);
      await refresh();
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <section>
      <div className="section-header">
        <div>
          <h2>{environment.name}</h2>
          {environment.description && <p className="muted">{environment.description}</p>}
        </div>
        <a className="button secondary" href={api.exportUrl(environment.id)}>
          Export .env
        </a>
      </div>

      <table className="var-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Value</th>
            <th>Secret</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {variables.map((v) => (
            <VariableRow
              key={v.id}
              envId={environment.id}
              variable={v}
              onChange={refresh}
              onError={onError}
            />
          ))}
          {variables.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                No variables yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <form onSubmit={handleAdd} className="inline-form add-var">
        <input
          value={draft.key}
          onChange={(e) => setDraft({ ...draft, key: e.target.value })}
          placeholder="KEY"
          required
        />
        <input
          value={draft.value}
          onChange={(e) => setDraft({ ...draft, value: e.target.value })}
          placeholder="value"
          type={draft.is_secret ? 'password' : 'text'}
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={draft.is_secret}
            onChange={(e) => setDraft({ ...draft, is_secret: e.target.checked })}
          />
          Secret
        </label>
        <button type="submit">Add variable</button>
      </form>
    </section>
  );
}
