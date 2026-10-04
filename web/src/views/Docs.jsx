import AiTask from '../components/AiTask.jsx';
import { useView } from '../useView.js';
import Loading from './Loading.jsx';

export default function Docs({ api, projectId, version, ai }) {
  const state = useView(api, projectId, 'docs', version);
  return (
    <Loading state={state}>
      {({ docs_map: map }) => {
        const files = Object.entries(map.undocumented);
        const readme = map.readme;
        return (
          <>
            <p>
              {map.public_names === 0
                ? 'No public functions or classes found.'
                : `${map.documented} of ${map.public_names} public names documented.`}
            </p>
            <h2>Names without docs</h2>
            {files.length === 0 && <p className="muted">None.</p>}
            <ul className="list files">
              {files.map(([path, names]) => (
                <li key={path}>
                  <code>{path}</code> <span className="muted">{names.join(', ')}</span>
                  <AiTask {...ai} request={{ task: 'docs', file: path }} label="Write docs with AI…" />
                </li>
              ))}
            </ul>
            <h2>README</h2>
            {!readme && <p>No README at the project root.</p>}
            {readme && !readme.checked && <p>{readme.path}: not checked (only Markdown is read).</p>}
            {readme?.checked && (
              <>
                <p>
                  {readme.path}: sections found: {readme.sections.join(', ') || 'none'}; missing:{' '}
                  {readme.missing_sections.join(', ') || 'none'}.
                </p>
                {readme.missing_scripts.length > 0 && (
                  <>
                    <p className="error">Commands in the README that would fail:</p>
                    <ul className="list">
                      {readme.missing_scripts.map((mention) => (
                        <li key={mention.command}>
                          <code>{mention.command}</code> (line {mention.line}): no package.json has
                          this script
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}
            {/* The license is never asked of the AI (D050): it alone needs no button. */}
            {(!readme || readme.missing_sections?.some((topic) => topic !== 'license')) && (
              <AiTask {...ai} request={{ task: 'readme' }} label="Write README sections with AI…" />
            )}
          </>
        );
      }}
    </Loading>
  );
}
