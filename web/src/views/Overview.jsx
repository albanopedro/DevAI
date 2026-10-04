import AiTask from '../components/AiTask.jsx';
import Findings from '../components/Findings.jsx';
import { useView } from '../useView.js';
import Loading from './Loading.jsx';

export default function Overview({ api, projectId, version, ai }) {
  const state = useView(api, projectId, 'analysis', version);
  return (
    <Loading state={state}>
      {({ project, checks }) => (
        <>
          <dl className="facts">
            <dt>Files</dt>
            <dd>
              {project.file_count} ({project.file_source})
            </dd>
            <dt>Git</dt>
            <dd>{project.has_git ? 'yes' : 'no'}</dd>
            <dt>Languages</dt>
            <dd>
              {project.languages.map((language) => `${language.name} (${language.files})`).join(', ') ||
                'none'}
            </dd>
            <dt>Frameworks</dt>
            <dd>{project.frameworks.join(', ') || 'none detected'}</dd>
            <dt>Tests</dt>
            <dd>
              {project.tests.files} file(s)
              {project.tests.frameworks.length > 0 && ` (${project.tests.frameworks.join(', ')})`}
            </dd>
          </dl>
          <h2>Findings</h2>
          <Findings findings={checks.findings} passed={checks.passed} />
          <h2>AI analysis</h2>
          <p className="muted">
            Sends a summary of the project (no source code) to a free model, after you see it.
          </p>
          <AiTask {...ai} request={{ task: 'analysis' }} label="Analyze with AI…" />
        </>
      )}
    </Loading>
  );
}
