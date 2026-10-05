import AiTask from '../components/AiTask.jsx';
import Findings from '../components/Findings.jsx';
import { useI18n } from '../i18n.js';
import { useView } from '../useView.js';
import Loading from './Loading.jsx';

export default function Review({ api, projectId, version, ai }) {
  const state = useView(api, projectId, 'review', version);
  const { t } = useI18n();
  return (
    <Loading state={state}>
      {({ review }) => (
        <>
          <p>{review.description}</p>
          {review.files.length === 0 ? (
            <p className="muted">{t('review.none')}</p>
          ) : (
            <ul className="list">
              {review.files.map((file) => (
                <li key={file.path}>
                  <code className="status">{file.untracked ? '?' : file.status}</code>{' '}
                  <code>{file.path}</code>{' '}
                  <span className="muted">
                    {file.additions != null && `+${file.additions} `}
                    {file.deletions != null && `-${file.deletions}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <h2>{t('review.checks')}</h2>
          <Findings findings={review.checks.findings} passed={review.checks.passed} />
          {review.files.length > 0 && (
            <>
              <h2>{t('review.aiTitle')}</h2>
              <p className="muted">{t('review.aiHint')}</p>
              <AiTask {...ai} request={{ task: 'review' }} label={t('review.aiButton')} />
            </>
          )}
        </>
      )}
    </Loading>
  );
}
