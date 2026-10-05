import { useState } from 'react';
import AiTask from '../components/AiTask.jsx';
import { useI18n } from '../i18n.js';

export default function Fix({ ai }) {
  const [ask, setAsk] = useState('');
  const [files, setFiles] = useState('');
  const { t } = useI18n();
  const names = files
    .split(/[\n,]/)
    .map((name) => name.trim())
    .filter(Boolean);
  return (
    <>
      <p className="muted">{t('fix.hint')}</p>
      <label className="field">
        {t('fix.what')}
        <textarea value={ask} onChange={(event) => setAsk(event.target.value)} rows={3} />
      </label>
      <label className="field">
        {t('fix.files')}
        <textarea value={files} onChange={(event) => setFiles(event.target.value)} rows={3} />
      </label>
      {ask.trim() && names.length > 0 && (
        <AiTask {...ai} request={{ task: 'fix', ask, files: names }} label={t('fix.aiButton')} />
      )}
    </>
  );
}
