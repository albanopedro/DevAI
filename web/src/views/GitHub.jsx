import { useEffect, useState } from 'react';
import AiTask from '../components/AiTask.jsx';
import Findings from '../components/Findings.jsx';
import { useI18n } from '../i18n.js';
import Loading from './Loading.jsx';

/** The project's open pull requests and issues, read through gh on this computer. */
export default function GitHub({ api, projectId, version, ai }) {
  const [state, setState] = useState({ loading: true });
  const { t } = useI18n();
  useEffect(() => {
    let current = true;
    setState({ loading: true });
    api.github(projectId).then(
      (data) => current && setState({ data }),
      (problem) => current && setState({ error: problem.message }),
    );
    return () => {
      current = false;
    };
  }, [api, projectId, version]);

  return (
    <Loading state={state}>
      {({ repo, pulls, issues, error }) =>
        error ? (
          <p className="error">{error}</p>
        ) : (
          <>
            <p className="muted">{t('github.intro', { repo })}</p>
            <h2>{t('github.pulls')}</h2>
            {pulls.length === 0 && <p className="muted">{t('none.found')}</p>}
            <ul className="list files">
              {pulls.map((pull) => (
                <li key={pull.number}>
                  <span>
                    <strong>#{pull.number}</strong> {pull.title}{' '}
                    <span className="muted">
                      ({pull.author}) {pull.base} ← {pull.head}
                      {pull.draft && t('github.draft')}
                    </span>
                  </span>
                  <PullChecks api={api} projectId={projectId} number={pull.number} />
                  <AiTask {...ai} request={{ task: 'pull', number: pull.number }} label={t('review.aiButton')} />
                </li>
              ))}
            </ul>
            <h2>{t('github.issues')}</h2>
            {issues.length === 0 && <p className="muted">{t('none.found')}</p>}
            <ul className="list files">
              {issues.map((issue) => (
                <li key={issue.number}>
                  <span>
                    <strong>#{issue.number}</strong> {issue.title}{' '}
                    <span className="muted">
                      ({issue.author}){issue.labels.length > 0 && ` [${issue.labels.join(', ')}]`}
                    </span>
                  </span>
                  <AiTask {...ai} request={{ task: 'issue', number: issue.number }} label={t('github.planButton')} />
                </li>
              ))}
            </ul>
          </>
        )
      }
    </Loading>
  );
}

/** The local checks of one pull request, loaded when asked. */
function PullChecks({ api, projectId, number }) {
  const [state, setState] = useState(null);
  const { t } = useI18n();
  if (state === null) {
    const load = () => {
      setState({ loading: true });
      api.pull(projectId, number).then(
        (data) => setState({ data }),
        (problem) => setState({ error: problem.message }),
      );
    };
    return (
      <button type="button" onClick={load}>
        {t('github.check')}
      </button>
    );
  }
  return (
    <div className="ai-task">
      <Loading state={state}>
        {({ review }) => (
          <>
            <p className="muted">{t('github.pullChecks', { count: review.files.length })}</p>
            <Findings findings={review.checks.findings} passed={review.checks.passed} />
          </>
        )}
      </Loading>
    </div>
  );
}
