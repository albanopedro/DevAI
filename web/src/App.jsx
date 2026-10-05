import { useEffect, useMemo, useState } from 'react';
import { createApi } from './api.js';
import { GitHubLink } from './components/AiResult.jsx';
import {
  initialLanguage,
  LANGUAGES,
  LanguageContext,
  LOCALES,
  saveLanguage,
  translate,
} from './i18n.js';
import Docs from './views/Docs.jsx';
import Fix from './views/Fix.jsx';
import GitHub from './views/GitHub.jsx';
import Overview from './views/Overview.jsx';
import Review from './views/Review.jsx';
import Tests from './views/Tests.jsx';

const TABS = [
  ['overview', Overview],
  ['review', Review],
  ['tests', Tests],
  ['docs', Docs],
  ['fix', Fix],
  ['github', GitHub],
];

const PROVIDERS = ['', 'opencode', 'ollama'];

export default function App({ token }) {
  const api = useMemo(() => (token ? createApi(token) : null), [token]);
  const [language, setLanguage] = useState(() => initialLanguage());
  const [projects, setProjects] = useState(null);
  const [projectId, setProjectId] = useState(0);
  const [tab, setTab] = useState('overview');
  const [provider, setProvider] = useState('');
  const [version, setVersion] = useState(0);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const t = (key, values) => translate(language, key, values);

  useEffect(() => {
    if (api) api.projects().then(setProjects, (problem) => setError(problem.message));
  }, [api]);

  useEffect(() => {
    document.documentElement.lang = LOCALES[language];
  }, [language]);

  const choose = (next) => {
    setLanguage(next);
    saveLanguage(next);
  };
  const switcher = <LanguageSwitch language={language} onChoose={choose} label={t('app.language')} />;

  if (!token) {
    return (
      <LanguageContext.Provider value={language}>
        <main className="page">
          <header className="top">
            <h1>DevAI</h1>
            {switcher}
          </header>
          <p>
            {t('app.noToken.before')}
            <code>devai serve</code>
            {t('app.noToken.after')}
          </p>
        </main>
      </LanguageContext.Provider>
    );
  }

  const refresh = () => setVersion((value) => value + 1);
  const View = TABS.find(([id]) => id === tab)[1];
  const onApplied = (done) => {
    setNotice(done);
    refresh();
  };
  const ai = { api, projectId, provider, onApplied };

  return (
    <LanguageContext.Provider value={language}>
      <main className="page">
        <header className="top">
          <h1>DevAI</h1>
          {projects && (
            <select
              aria-label={t('app.project')}
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
          <select
            aria-label={t('app.provider')}
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
          >
            {PROVIDERS.map((value) => (
              <option key={value} value={value}>
                {t(`provider.${value || 'default'}`)}
              </option>
            ))}
          </select>
          <button type="button" onClick={refresh}>
            {t('app.refresh')}
          </button>
          {switcher}
        </header>
        {error && <p className="error">{error}</p>}
        {notice && (
          <div className="notice" role="status">
            {notice.url !== undefined ? (
              <span>
                {t('notice.posted')}
                <GitHubLink url={notice.url} />
                {t('notice.postedAfter')}
              </span>
            ) : (
              <span>
                {t('notice.written', { files: notice.files.join(', ') })}
                <code>{notice.undo}</code>
                {t('notice.nothingCommitted')}
              </span>
            )}
            <button type="button" onClick={() => setNotice(null)}>
              {t('app.dismiss')}
            </button>
          </div>
        )}
        {projects && (
          <>
            <p className="muted path" title={projects[projectId]?.path}>
              {shortPath(projects[projectId]?.path ?? '')}
            </p>
            <nav className="tabs">
              {TABS.map(([id]) => (
                <button
                  key={id}
                  type="button"
                  className={id === tab ? 'tab active' : 'tab'}
                  aria-pressed={id === tab}
                  onClick={() => setTab(id)}
                >
                  {t(`tab.${id}`)}
                </button>
              ))}
            </nav>
            <section className="view" key={`${projectId}-${tab}`}>
              <View api={api} projectId={projectId} version={version} ai={ai} />
            </section>
          </>
        )}
        <footer className="muted">{t('app.footer')}</footer>
      </main>
    </LanguageContext.Provider>
  );
}

/** EN | PT: switches every text on the page; the browser remembers the choice. */
export function LanguageSwitch({ language, onChoose, label }) {
  return (
    <div className="switch" role="group" aria-label={label}>
      {Object.entries(LANGUAGES).map(([code, name]) => (
        <button
          key={code}
          type="button"
          title={name}
          aria-label={name}
          aria-pressed={code === language}
          className={code === language ? 'active' : undefined}
          onClick={() => onChoose(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

/** The last two folders of a path: long paths fill the header (the full one is the tooltip). */
export function shortPath(path) {
  const parts = path.split('/').filter(Boolean);
  return parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : path;
}
