import { useI18n } from '../i18n.js';
import Diff from './Diff.jsx';
import { Severity } from './Findings.jsx';

/** What the AI answered, after DevAI's checks. All of it is shown as text. */
export default function AiResult({ answer }) {
  const { t, number } = useI18n();
  const { task, result } = answer;
  const ai = result.ai;
  if (!ai) return <p className="muted">{t('result.none')}</p>;
  return (
    <div className="ai-result">
      <p className="muted">
        {t('result.usage', {
          model: ai.model,
          input: number(ai.usage.input_tokens),
          output: number(ai.usage.output_tokens),
        })}
      </p>
      {ai.rejected && <p className="error">{t('result.rejected', { reason: ai.rejected })}</p>}
      {task === 'analysis' && <Analysis report={ai.report} />}
      {task === 'review' && <Review report={ai.report} discarded={ai.discarded_issues} />}
      {task === 'docs' && (
        <Proposal
          diff={ai.diff}
          added={ai.added}
          dropped={ai.dropped}
          checked={t(result.docs.file.endsWith('.py') ? 'result.docsCheckedPython' : 'result.docsCheckedJs')}
        />
      )}
      {task === 'readme' && (
        <Proposal
          diff={ai.diff}
          added={ai.added.map((item) => `${item.heading} (${t(`topic.${item.topic}`)})`)}
          dropped={ai.dropped.map((item) => ({ name: item.section, reason: item.reason }))}
          links={ai.links}
          leftOut={result.left_out}
          checked={t(ai.creates ? 'result.readmeCreated' : 'result.readmeAdded')}
        />
      )}
      {task === 'fix' && <Fix proposal={ai.proposal} diffs={ai.diffs} />}
      {task === 'pull' && (
        <>
          <p>
            <strong>
              #{result.pull_request.number} {result.pull_request.title}
            </strong>{' '}
            <GitHubLink url={result.pull_request.url} />
          </p>
          <Review report={ai.report} discarded={ai.discarded_issues} />
        </>
      )}
      {task === 'issue' && <Plan plan={ai.plan} dropped={ai.files_dropped} />}
      {result.comment_blocked && (
        <p className="error">{t('result.commentBlocked', { reason: result.comment_blocked })}</p>
      )}
      {task === 'tests' && <Tests ai={ai} runCommand={result.run_command} />}
      <List title={t('result.notes')} items={ai.proposal?.notes ?? []} />
      <p className="muted">{t('result.writtenByAi')}</p>
    </div>
  );
}

function Analysis({ report }) {
  const { t } = useI18n();
  return (
    <>
      <p>{report.summary}</p>
      <h4>{t('result.risks')}</h4>
      <ul className="list">
        {report.risks.map((risk, index) => (
          <li key={index}>
            <Severity level={risk.severity} /> <strong>{risk.title}</strong>: {risk.explanation}
          </li>
        ))}
      </ul>
      <h4>{t('result.recommendations')}</h4>
      <ol>
        {report.recommendations.map((step, index) => (
          <li key={index}>
            <strong>{step.title}</strong> {t('result.effort', { effort: t(`effort.${step.effort}`) })}:{' '}
            {step.rationale}
          </li>
        ))}
      </ol>
      <List title={t('result.limitations')} items={report.limitations} />
    </>
  );
}

function Review({ report, discarded }) {
  const { t } = useI18n();
  return (
    <>
      <p>{report.summary}</p>
      <h4>{t('result.issues')}</h4>
      {report.issues.length === 0 && <p className="muted">{t('result.noneFound')}</p>}
      <ul className="list">
        {report.issues.map((issue, index) => (
          <li key={index}>
            <Severity level={issue.severity} /> <strong>{issue.title}</strong>{' '}
            <code className="where">
              {issue.file}
              {issue.line ? `:${issue.line}` : ''}
            </code>
            <div>{issue.explanation}</div>
            <div className="muted">{t('result.suggestion', { text: issue.suggestion })}</div>
          </li>
        ))}
      </ul>
      {discarded > 0 && <p className="muted">{t('result.discarded', { count: discarded })}</p>}
      <List title={t('result.suggestedTests')} items={report.suggested_tests} />
      <List title={t('result.limitations')} items={report.limitations} />
    </>
  );
}

function Proposal({ diff, added = [], dropped = [], links = [], leftOut = [], checked }) {
  const { t } = useI18n();
  return (
    <>
      {diff ? <Diff text={diff} /> : <p className="muted">{t('result.noChange')}</p>}
      {added.length > 0 && <p>{t('result.added', { items: added.join(', ') })}</p>}
      {diff && <p className="checked">{checked}</p>}
      <List title={t('result.notUsed')} items={dropped.map((item) => `${item.name}: ${item.reason}`)} />
      <List title={t('result.links')} items={links} />
      <List
        title={t('result.notAsked')}
        items={leftOut.map((item) => `${t(`topic.${item.topic}`)}: ${item.reason}`)}
      />
    </>
  );
}

function Plan({ plan, dropped }) {
  const { t } = useI18n();
  return (
    <>
      <p>{plan.summary}</p>
      <List title={t('result.filesToLook')} items={plan.files.map((file) => `${file.path}: ${file.why}`)} />
      {dropped > 0 && <p className="muted">{t('result.filesDropped', { count: dropped })}</p>}
      {plan.steps.length > 0 && (
        <>
          <h4>{t('result.steps')}</h4>
          <ol>
            {plan.steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </>
      )}
      <List title={t('result.tests')} items={plan.tests} />
      <List title={t('result.questions')} items={plan.questions} />
    </>
  );
}

/** A link only to GitHub itself; any other address is shown as text. */
export function GitHubLink({ url }) {
  if (typeof url !== 'string' || !url.startsWith('https://github.com/')) {
    return <code>{String(url ?? '')}</code>;
  }
  return (
    <a href={url} target="_blank" rel="noreferrer noopener">
      {url}
    </a>
  );
}

function Fix({ proposal, diffs }) {
  const { t } = useI18n();
  const paths = Object.keys(diffs ?? {});
  return (
    <>
      <p>{proposal.summary}</p>
      {paths.length === 0 && <p className="muted">{t('result.noFixChange')}</p>}
      {paths.map((path) => (
        <Diff key={path} text={diffs[path]} />
      ))}
      <List title={t('result.risks')} items={proposal.risks} />
      <List title={t('result.howToVerify')} items={proposal.tests} />
    </>
  );
}

function Tests({ ai, runCommand }) {
  const { t } = useI18n();
  return (
    <>
      {ai.path && (
        <p>
          {t('result.newFile')}
          <code>{ai.path}</code>
        </p>
      )}
      <pre className="code">{ai.proposal.content}</pre>
      {runCommand && (
        <p>
          {t('result.runThem')}
          <code>{runCommand}</code>
          {t('result.neverRuns')}
        </p>
      )}
    </>
  );
}

function List({ title, items }) {
  if (!items || items.length === 0) return null;
  return (
    <>
      <h4>{title}</h4>
      <ul className="list">
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </>
  );
}
