import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { envApi, type Environment, type Variable, type VariableInput } from '../api/env';
import VariableRow from './VariableRow';

const EMPTY: VariableInput = { key: '', value: '', is_secret: false };

interface Props {
  environment: Environment;
  onChange: () => Promise<void>;
  onError: (msg: string) => void;
}

export default function VariableTable({ environment, onChange, onError }: Props) {
  const [variables, setVariables] = useState<Variable[]>([]);
  const [draft, setDraft] = useState<VariableInput>(EMPTY);

  const load = useCallback(async () => {
    try {
      setVariables(await envApi.listVariables(environment.id));
    } catch (err) {
      onError((err as Error).message);
    }
  }, [environment.id, onError]);

  useEffect(() => {
    load();
  }, [load]);

  async function refresh() {
    await load();
    await onChange();
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    try {
      await envApi.createVariable(environment.id, draft);
      setDraft(EMPTY);
      await refresh();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  return (
    <section>
      <div className="section-header">
        <div>
          <h2>{environment.name}</h2>
          {environment.description && <p className="muted">{environment.description}</p>}
        </div>
        <a className="button secondary" href={envApi.exportUrl(environment.id)}>
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
            <VariableRow key={v.id} envId={environment.id} variable={v} onChange={refresh} onError={onError} />
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
        <input value={draft.key} onChange={(e) => setDraft({ ...draft, key: e.target.value })} placeholder="KEY" aria-label="Key" required />
        <input
          value={draft.value}
          onChange={(e) => setDraft({ ...draft, value: e.target.value })}
          placeholder="value"
          aria-label="Value"
          type={draft.is_secret ? 'password' : 'text'}
        />
        <label className="checkbox">
          <input type="checkbox" checked={draft.is_secret} onChange={(e) => setDraft({ ...draft, is_secret: e.target.checked })} />
          Secret
        </label>
        <button type="submit">Add variable</button>
      </form>
    </section>
  );
}
