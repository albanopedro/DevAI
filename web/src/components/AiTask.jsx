import { useState } from 'react';
import { consentQuestion, useI18n } from '../i18n.js';
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
  const { t, language, number } = useI18n();

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
      {step === 'preparing' && <p className="muted">{t('ai.preparing')}</p>}

      {(step === 'preview' || step === 'sending') && preview && (
        <section className="panel" aria-label="what would be sent">
          <h3>{t('ai.before')}</h3>
          {/* English: the server's question, word for word as in the terminal. */}
          <p>{language === 'en' ? preview.question : consentQuestion(t, number, preview)}</p>
          <p className={preview.leaves_machine ? 'badge leaves' : 'badge stays'}>
            {preview.leaves_machine ? t('ai.leaves') : t('ai.stays')}
            {preview.destination}
          </p>
          {preview.data_note && <p className="muted">{t('ai.note', { note: preview.data_note })}</p>}
          <p className="muted">
            {t('ai.size', {
              characters: number(preview.characters),
              tokens: number(preview.tokens),
              redacted: preview.redacted_lines,
            })}
          </p>
          <details>
            <summary>{t('ai.exactly')}</summary>
            <pre className="code">{JSON.stringify(preview.context, null, 2)}</pre>
          </details>
          {step === 'sending' ? (
            <p className="muted">{t('ai.waiting')}</p>
          ) : (
            <div className="actions">
              <button type="button" className="primary" onClick={send}>
                {t('ai.send')}
              </button>
              <button type="button" onClick={close}>
                {t('ai.cancel')}
              </button>
            </div>
          )}
        </section>
      )}

      {['result', 'confirming', 'applying', 'applied'].includes(step) && answer && (
        <section className="panel" aria-label="AI answer">
          <h3>{t('ai.answer')}</h3>
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
              {t('ai.posted', { files: applied.files.join(', ') })}
              <GitHubLink url={applied.url} />.
            </p>
          )}
          {step === 'applied' && applied && applied.url === undefined && (
            <p className="done">
              {t('ai.done', { files: applied.files.join(', ') })}
              <code>{applied.undo}</code>
              {t('notice.nothingCommitted')}
            </p>
          )}
          {step !== 'applied' && (
            <button type="button" onClick={close}>
              {t('ai.close')}
            </button>
          )}
        </section>
      )}
    </div>
  );
}

function ApplyBox({ apply, step, onAsk, onConfirm, onCancel }) {
  const { t } = useI18n();
  const files = apply.files.join(', ');
  if (apply.blocked) {
    return (
      <div className="apply">
        <button type="button" disabled>
          {t('apply.apply')}
        </button>
        <p className="muted">{t('apply.cant', { reason: apply.blocked })}</p>
      </div>
    );
  }
  if (step === 'result') {
    const label = t({ create: 'apply.create', comment: 'apply.comment' }[apply.kind] ?? 'apply.write', {
      files,
    });
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
          {t('apply.commentBefore', { files })}
          <strong>{apply.account}</strong>
          {t('apply.commentAfter')}
        </p>
        <pre className="code">{apply.preview}</pre>
        <div className="actions">
          <button type="button" className="primary" onClick={onConfirm} disabled={step === 'applying'}>
            {t('apply.yesPost')}
          </button>
          <button type="button" onClick={onCancel} disabled={step === 'applying'}>
            {t('ai.cancel')}
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="apply confirm" role="alertdialog" aria-label="confirm">
      <p>{t(apply.kind === 'create' ? 'apply.createConfirm' : 'apply.writeConfirm', { files })}</p>
      <div className="actions">
        <button type="button" className="primary" onClick={onConfirm} disabled={step === 'applying'}>
          {t(apply.kind === 'create' ? 'apply.yesCreate' : 'apply.yesWrite')}
        </button>
        <button type="button" onClick={onCancel} disabled={step === 'applying'}>
          {t('ai.cancel')}
        </button>
      </div>
    </div>
  );
}
