import { useCallback, useEffect, useState } from 'react';
import { envApi, type Environment } from '../api/env';
import EnvironmentSidebar from './EnvironmentSidebar';
import VariableTable from './VariableTable';
import './env.css';

export default function EnvironmentsPage() {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState('');

  const loadEnvironments = useCallback(async () => {
    try {
      const envs = await envApi.listEnvironments();
      setEnvironments(envs);
      setSelectedId((cur) => (envs.some((e) => e.id === cur) ? cur : (envs[0]?.id ?? null)));
      setError('');
    } catch (e) {
      setError(`Could not load environments: ${(e as Error).message}`);
    }
  }, []);

  useEffect(() => {
    loadEnvironments();
  }, [loadEnvironments]);

  const selected = environments.find((e) => e.id === selectedId) ?? null;

  return (
    <div className="env-page">
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
