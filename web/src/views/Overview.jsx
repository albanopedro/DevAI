import AiTask from '../components/AiTask.jsx';
import Findings from '../components/Findings.jsx';
import { useI18n } from '../i18n.js';
import { useView } from '../useView.js';
import Loading from './Loading.jsx';

export default function Overview({ api, projectId, version, ai }) {
  const state = useView(api, projectId, 'analysis', version);
  const { t } = useI18n();
  return (
    <Loading state={state}>
      {({ project, checks }) => (
        <>
          <dl className="facts">
            <dt>{t('overview.files')}</dt>
            <dd>
              {project.file_count} ({project.file_source})
            </dd>
            <dt>{t('overview.git')}</dt>
            <dd>{project.has_git ? t('yes') : t('no')}</dd>
            <dt>{t('overview.languages')}</dt>
            <dd>
              {project.languages.map((language) => `${language.name} (${language.files})`).join(', ') ||
                t('none')}
            </dd>
            <dt>{t('overview.frameworks')}</dt>
            <dd>{project.frameworks.join(', ') || t('overview.noneDetected')}</dd>
            <dt>{t('overview.tests')}</dt>
            <dd>
              {t('filesCount', { count: project.tests.files })}
              {project.tests.frameworks.length > 0 && ` (${project.tests.frameworks.join(', ')})`}
            </dd>
          </dl>
          <h2>{t('overview.findings')}</h2>
          <Findings findings={checks.findings} passed={checks.passed} />
          <h2>{t('overview.aiTitle')}</h2>
          <p className="muted">{t('overview.aiHint')}</p>
          <AiTask {...ai} request={{ task: 'analysis' }} label={t('overview.aiButton')} />
        </>
      )}
    </Loading>
  );
}
