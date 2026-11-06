import { useState, type FormEvent } from 'react';
import { envApi, type Environment } from '../api/env';

interface Props {
  environments: Environment[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onChange: () => Promise<void>;
  onError: (msg: string) => void;
}

export default function EnvironmentSidebar({ environments, selectedId, onSelect, onChange, onError }: Props) {
  const [name, setName] = useState('');

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const env = await envApi.createEnvironment({ name: name.trim() });
      setName('');
      await onChange();
      onSelect(env.id);
    } catch (err) {
      onError((err as Error).message);
    }
  }

  async function handleDelete(env: Environment) {
    if (!window.confirm(`Delete environment "${env.name}" and all its variables?`)) return;
    try {
      await envApi.deleteEnvironment(env.id);
      await onChange();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  return (
    <aside className="sidebar">
      <h2>Environments</h2>
      <ul className="env-list">
        {environments.map((env) => (
          <li key={env.id} className={env.id === selectedId ? 'active' : ''}>
            <button className="env-item" onClick={() => onSelect(env.id)}>
              <span>{env.name}</span>
              <span className="badge">{env.variable_count}</span>
            </button>
            <button className="icon-btn" title="Delete" aria-label={`Delete ${env.name}`} onClick={() => handleDelete(env)}>
              ×
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={handleCreate} className="inline-form">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New environment" aria-label="New environment" />
        <button type="submit">Add</button>
      </form>
    </aside>
  );
}
