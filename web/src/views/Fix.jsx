import { useState } from 'react';
import AiTask from '../components/AiTask.jsx';

export default function Fix({ ai }) {
  const [ask, setAsk] = useState('');
  const [files, setFiles] = useState('');
  const names = files
    .split(/[\n,]/)
    .map((name) => name.trim())
    .filter(Boolean);
  return (
    <>
      <p className="muted">
        Describe a change and name up to 3 files. The AI proposes it as a diff; nothing is written
        until you confirm, and only if those files are committed and unchanged.
      </p>
      <label className="field">
        What should change?
        <textarea value={ask} onChange={(event) => setAsk(event.target.value)} rows={3} />
      </label>
      <label className="field">
        Files (paths in the project, one per line)
        <textarea value={files} onChange={(event) => setFiles(event.target.value)} rows={3} />
      </label>
      {ask.trim() && names.length > 0 && (
        <AiTask {...ai} request={{ task: 'fix', ask, files: names }} label="Propose a fix with AI…" />
      )}
    </>
  );
}
