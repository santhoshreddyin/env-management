import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client.js';
import EnvironmentSidebar from './components/EnvironmentSidebar.jsx';
import VariableTable from './components/VariableTable.jsx';

export default function App() {
  const [environments, setEnvironments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState('');

  const loadEnvironments = useCallback(async () => {
    try {
      const envs = await api.listEnvironments();
      setEnvironments(envs);
      setSelectedId((cur) => (envs.some((e) => e.id === cur) ? cur : envs[0]?.id ?? null));
      setError('');
    } catch (e) {
      setError(`Could not load environments: ${e.message}`);
    }
  }, []);

  useEffect(() => {
    loadEnvironments();
  }, [loadEnvironments]);

  const selected = environments.find((e) => e.id === selectedId) || null;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Env Management</h1>
      </header>
      {error && <div className="alert">{error}</div>}
      <div className="layout">
        <EnvironmentSidebar
          environments={environments}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onChange={loadEnvironments}
          onError={setError}
        />
        <main className="content">
          {selected ? (
            <VariableTable environment={selected} onChange={loadEnvironments} onError={setError} />
          ) : (
            <p className="muted">Create an environment to get started.</p>
          )}
        </main>
      </div>
    </div>
  );
}
