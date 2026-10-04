import { useEffect, useMemo, useState } from 'react';
import { createApi } from './api.js';
import Docs from './views/Docs.jsx';
import Fix from './views/Fix.jsx';
import Overview from './views/Overview.jsx';
import Review from './views/Review.jsx';
import Tests from './views/Tests.jsx';

const TABS = [
  ['overview', 'Overview', Overview],
  ['review', 'Review', Review],
  ['tests', 'Tests', Tests],
  ['docs', 'Docs', Docs],
  ['fix', 'Fix', Fix],
];

const PROVIDERS = [
  ['', 'AI: default'],
  ['opencode', 'AI: OpenCode free model (online)'],
  ['ollama', 'AI: Ollama (this computer)'],
];

export default function App({ token }) {
  const api = useMemo(() => (token ? createApi(token) : null), [token]);
  const [projects, setProjects] = useState(null);
  const [projectId, setProjectId] = useState(0);
  const [tab, setTab] = useState('overview');
  const [provider, setProvider] = useState('');
  const [version, setVersion] = useState(0);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    if (api) api.projects().then(setProjects, (problem) => setError(problem.message));
  }, [api]);

  if (!token) {
    return (
      <main className="page">
        <h1>DevAI</h1>
        <p>
          Open this page with the address <code>devai serve</code> printed in your terminal: it
          carries the key that lets this page talk to DevAI.
        </p>
      </main>
    );
  }

  const refresh = () => setVersion((value) => value + 1);
  const View = TABS.find(([id]) => id === tab)[2];
  const onApplied = (done) => {
    setNotice(done);
    refresh();
  };
  const ai = { api, projectId, provider, onApplied };

  return (
    <main className="page">
      <header className="top">
        <h1>DevAI</h1>
        {projects && (
          <select
            aria-label="project"
            value={projectId}
            onChange={(event) => setProjectId(Number(event.target.value))}
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        )}
        <select aria-label="AI provider" value={provider} onChange={(event) => setProvider(event.target.value)}>
          {PROVIDERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <button type="button" onClick={refresh}>
          Refresh
        </button>
      </header>
      {error && <p className="error">{error}</p>}
      {notice && (
        <div className="notice" role="status">
          <span>
            Written: {notice.files.join(', ')}. Undo with: <code>{notice.undo}</code>. Nothing was
            committed.
          </span>
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      {projects && (
        <>
          <p className="muted path">{projects[projectId]?.path}</p>
          <nav className="tabs">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={id === tab ? 'tab active' : 'tab'}
                aria-pressed={id === tab}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          <section className="view" key={`${projectId}-${tab}`}>
            <View api={api} projectId={projectId} version={version} ai={ai} />
          </section>
        </>
      )}
      <footer className="muted">
        Runs on this computer only. Nothing goes to an AI until you press Send on a preview, and
        nothing is written until you confirm.
      </footer>
    </main>
  );
}
