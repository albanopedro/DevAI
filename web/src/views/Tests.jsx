import AiTask from '../components/AiTask.jsx';
import { useView } from '../useView.js';
import Loading from './Loading.jsx';

export default function Tests({ api, projectId, version, ai }) {
  const state = useView(api, projectId, 'tests', version);
  return (
    <Loading state={state}>
      {({ test_map: map }) => {
        const untested = map.untested_symbols;
        const files = [...new Set([...map.without_tests, ...Object.keys(untested)])];
        return (
          <>
            <p>
              {map.test_files} test file(s)
              {map.frameworks.length > 0 && ` (${map.frameworks.join(', ')})`}, {map.sources_checked}{' '}
              source file(s) checked.
            </p>
            {files.length === 0 && <p className="muted">Every checked file seems to have tests.</p>}
            <ul className="list files">
              {files.map((path) => (
                <li key={path}>
                  <code>{path}</code>
                  {map.without_tests.includes(path) && <span className="tag">no test file</span>}
                  {untested[path] && (
                    <span className="muted"> names no test mentions: {untested[path].join(', ')}</span>
                  )}
                  <AiTask {...ai} request={{ task: 'tests', file: path }} label="Write tests with AI…" />
                </li>
              ))}
            </ul>
            <p className="muted">
              An estimate from file and symbol names. DevAI never runs tests: you do.
            </p>
          </>
        );
      }}
    </Loading>
  );
}
