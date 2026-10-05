import AiTask from '../components/AiTask.jsx';
import { useI18n } from '../i18n.js';
import { useView } from '../useView.js';
import Loading from './Loading.jsx';

export default function Docs({ api, projectId, version, ai }) {
  const state = useView(api, projectId, 'docs', version);
  const { t } = useI18n();
  const topics = (names) => names.map((name) => t(`topic.${name}`)).join(', ') || t('none');
  return (
    <Loading state={state}>
      {({ docs_map: map }) => {
        const files = Object.entries(map.undocumented);
        const readme = map.readme;
        return (
          <>
            <p>
              {map.public_names === 0
                ? t('docs.noNames')
                : t('docs.documented', { documented: map.documented, total: map.public_names })}
            </p>
            <h2>{t('docs.withoutDocs')}</h2>
            {files.length === 0 && <p className="muted">{t('none.found')}</p>}
            <ul className="list files">
              {files.map(([path, names]) => (
                <li key={path}>
                  <code>{path}</code> <span className="muted">{names.join(', ')}</span>
                  <AiTask {...ai} request={{ task: 'docs', file: path }} label={t('docs.aiButton')} />
                </li>
              ))}
            </ul>
            <h2>README</h2>
            {!readme && <p>{t('docs.noReadme')}</p>}
            {readme && !readme.checked && <p>{t('docs.notChecked', { path: readme.path })}</p>}
            {readme?.checked && (
              <>
                <p>
                  {t('docs.sections', {
                    path: readme.path,
                    found: topics(readme.sections),
                    missing: topics(readme.missing_sections),
                  })}
                </p>
                {readme.missing_scripts.length > 0 && (
                  <>
                    <p className="error">{t('docs.failing')}</p>
                    <ul className="list">
                      {readme.missing_scripts.map((mention) => (
                        <li key={mention.command}>
                          <code>{mention.command}</code>
                          {t('docs.failingItem', { line: mention.line })}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}
            {/* The license is never asked of the AI (D050): it alone needs no button. */}
            {(!readme || readme.missing_sections?.some((topic) => topic !== 'license')) && (
              <AiTask {...ai} request={{ task: 'readme' }} label={t('docs.readmeButton')} />
            )}
          </>
        );
      }}
    </Loading>
  );
}
