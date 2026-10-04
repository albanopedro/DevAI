import AiTask from '../components/AiTask.jsx';
import Findings from '../components/Findings.jsx';
import { useView } from '../useView.js';
import Loading from './Loading.jsx';

export default function Review({ api, projectId, version, ai }) {
  const state = useView(api, projectId, 'review', version);
  return (
    <Loading state={state}>
      {({ review }) => (
        <>
          <p>{review.description}</p>
          {review.files.length === 0 ? (
            <p className="muted">No changes to review.</p>
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
          <h2>Checks</h2>
          <Findings findings={review.checks.findings} passed={review.checks.passed} />
          {review.files.length > 0 && (
            <>
              <h2>AI review</h2>
              <p className="muted">Sends the changed lines (secrets hidden), after you see them.</p>
              <AiTask {...ai} request={{ task: 'review' }} label="Review with AI…" />
            </>
          )}
        </>
      )}
    </Loading>
  );
}
