import AiTask from '../components/AiTask.jsx';
import { useI18n } from '../i18n.js';
import { useView } from '../useView.js';
import Loading from './Loading.jsx';

export default function Tests({ api, projectId, version, ai }) {
  const state = useView(api, projectId, 'tests', version);
  const { t } = useI18n();
  return (
    <Loading state={state}>
      {({ test_map: map }) => {
        const untested = map.untested_symbols;
        const files = [...new Set([...map.without_tests, ...Object.keys(untested)])];
        const frameworks = map.frameworks.length > 0 ? ` (${map.frameworks.join(', ')})` : '';
        return (
          <>
            <p>
              {t('tests.summary', {
                tests: map.test_files,
                frameworks,
                sources: map.sources_checked,
              })}
            </p>
            {files.length === 0 && <p className="muted">{t('tests.allCovered')}</p>}
            <ul className="list files">
              {files.map((path) => (
                <li key={path}>
                  <code>{path}</code>
                  {map.without_tests.includes(path) && <span className="tag">{t('tests.noTestFile')}</span>}
                  {untested[path] && (
                    <span className="muted">{t('tests.untested', { names: untested[path].join(', ') })}</span>
                  )}
                  <AiTask {...ai} request={{ task: 'tests', file: path }} label={t('tests.aiButton')} />
                </li>
              ))}
            </ul>
            <p className="muted">{t('tests.estimate')}</p>
          </>
        );
      }}
    </Loading>
  );
}
