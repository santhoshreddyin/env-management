import { useState } from 'react';
import { api } from '../api/client.js';

export default function EnvironmentSidebar({ environments, selectedId, onSelect, onChange, onError }) {
  const [name, setName] = useState('');

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const env = await api.createEnvironment({ name: name.trim() });
      setName('');
      await onChange();
      onSelect(env.id);
    } catch (err) {
      onError(err.message);
    }
  }

  async function handleDelete(env) {
    if (!window.confirm(`Delete environment "${env.name}" and all its variables?`)) return;
    try {
      await api.deleteEnvironment(env.id);
      await onChange();
    } catch (err) {
      onError(err.message);
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
            <button className="icon-btn" title="Delete" onClick={() => handleDelete(env)}>
              ×
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={handleCreate} className="inline-form">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New environment" />
        <button type="submit">Add</button>
      </form>
    </aside>
  );
}
