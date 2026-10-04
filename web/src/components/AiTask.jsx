import { useState } from 'react';
import AiResult, { GitHubLink } from './AiResult.jsx';

/**
 * One AI task, in the same steps as the terminal:
 * prepare (nothing sent) → the user reads the preview and clicks Send →
 * the checked answer → the user clicks Apply and confirms → written.
 * The page never sends file content to write: only the id of a proposal
 * the server keeps.
 */
export default function AiTask({ api, projectId, request, label, provider, onApplied }) {
  const [step, setStep] = useState('idle');
  const [preview, setPreview] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [applied, setApplied] = useState(null);
  const [error, setError] = useState(null);

  async function attempt(busy, work, onFailure = 'idle') {
    setError(null);
    setStep(busy);
    try {
      await work();
    } catch (problem) {
      setError(problem.message);
      setStep(onFailure);
    }
  }

  const prepare = () =>
    attempt('preparing', async () => {
      setAnswer(null);
      setApplied(null);
      const body = provider ? { ...request, provider } : request;
      setPreview(await api.prepare(projectId, body));
      setStep('preview');
    });

  // A preview is sent once: after a failure, start again from a new one.
  const send = () =>
    attempt('sending', async () => {
      setAnswer(await api.send(preview.prepared_id));
      setStep('result');
    });

  const apply = () =>
    attempt(
      'applying',
      async () => {
        const done = await api.apply(answer.apply.outcome_id);
        setApplied(done);
        setStep('applied');
        onApplied?.(done); // the page shows it: this panel may go once the view reloads
      },
      'result',
    );

  const close = () => {
    setStep('idle');
    setError(null);
  };

  return (
    <div className="ai-task">
      {(step === 'idle' || step === 'applied') && (
        <button type="button" onClick={prepare}>
          {label}
        </button>
      )}
      {error && <p className="error">{error}</p>}
      {step === 'preparing' && <p className="muted">Preparing what would be sent… (nothing is sent yet)</p>}

      {(step === 'preview' || step === 'sending') && preview && (
        <section className="panel" aria-label="what would be sent">
          <h3>Before anything is sent</h3>
          <p>{preview.question}</p>
          <p className={preview.leaves_machine ? 'badge leaves' : 'badge stays'}>
            {preview.leaves_machine ? 'Leaves this computer: ' : 'Stays on this computer: '}
            {preview.destination}
          </p>
          {preview.data_note && <p className="muted">Note: {preview.data_note}.</p>}
          <p className="muted">
            {preview.characters.toLocaleString()} characters (~{preview.tokens.toLocaleString()}{' '}
            tokens), {preview.redacted_lines} line(s) hidden as possible secrets.
          </p>
          <details>
            <summary>Exactly what would be sent</summary>
            <pre className="code">{JSON.stringify(preview.context, null, 2)}</pre>
          </details>
          {step === 'sending' ? (
            <p className="muted">Waiting for the AI… this can take a minute.</p>
          ) : (
            <div className="actions">
              <button type="button" className="primary" onClick={send}>
                Send
              </button>
              <button type="button" onClick={close}>
                Cancel
              </button>
            </div>
          )}
        </section>
      )}

      {['result', 'confirming', 'applying', 'applied'].includes(step) && answer && (
        <section className="panel" aria-label="AI answer">
          <h3>AI answer</h3>
          <AiResult answer={answer} />
          {answer.apply && step !== 'applied' && (
            <ApplyBox
              apply={answer.apply}
              step={step}
              onAsk={() => setStep('confirming')}
              onConfirm={apply}
              onCancel={() => setStep('result')}
            />
          )}
          {step === 'applied' && applied && applied.url !== undefined && (
            <p className="done">
              Posted on {applied.files.join(', ')}: <GitHubLink url={applied.url} />.
            </p>
          )}
          {step === 'applied' && applied && applied.url === undefined && (
            <p className="done">
              Done: {applied.files.join(', ')}. Undo with: <code>{applied.undo}</code>. Nothing
              was committed.
            </p>
          )}
          {step !== 'applied' && (
            <button type="button" onClick={close}>
              Close
            </button>
          )}
        </section>
      )}
    </div>
  );
}

function ApplyBox({ apply, step, onAsk, onConfirm, onCancel }) {
  const files = apply.files.join(', ');
  if (apply.blocked) {
    return (
      <div className="apply">
        <button type="button" disabled>
          Apply
        </button>
        <p className="muted">Can't apply now: {apply.blocked}.</p>
      </div>
    );
  }
  if (step === 'result') {
    const label = {
      create: `Create ${files}…`,
      comment: `Post as a comment on ${files}…`,
    }[apply.kind] ?? `Apply to ${files}…`;
    return (
      <div className="apply">
        <button type="button" className="primary" onClick={onAsk}>
          {label}
        </button>
      </div>
    );
  }
  if (apply.kind === 'comment') {
    return (
      <div className="apply confirm" role="alertdialog" aria-label="confirm">
        <p>
          Post this comment on {files} as <strong>{apply.account}</strong>? Everyone who can see it
          on GitHub will see it. Mentions and #references are broken on purpose.
        </p>
        <pre className="code">{apply.preview}</pre>
        <div className="actions">
          <button type="button" className="primary" onClick={onConfirm} disabled={step === 'applying'}>
            Yes, post it
          </button>
          <button type="button" onClick={onCancel} disabled={step === 'applying'}>
            Cancel
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="apply confirm" role="alertdialog" aria-label="confirm">
      <p>
        {apply.kind === 'create'
          ? `Create ${files}? It is created only if it doesn't exist yet.`
          : `Write these changes to ${files}? DevAI checks again that nothing changed since it read them. Undo with git restore.`}
      </p>
      <div className="actions">
        <button type="button" className="primary" onClick={onConfirm} disabled={step === 'applying'}>
          {apply.kind === 'create' ? 'Yes, create it' : 'Yes, write it'}
        </button>
        <button type="button" onClick={onCancel} disabled={step === 'applying'}>
          Cancel
        </button>
      </div>
    </div>
  );
}
