import Diff from './Diff.jsx';
import { Severity } from './Findings.jsx';

/** What the AI answered, after DevAI's checks. All of it is shown as text. */
export default function AiResult({ answer }) {
  const { task, result } = answer;
  const ai = result.ai;
  if (!ai) return <p className="muted">No answer.</p>;
  return (
    <div className="ai-result">
      <p className="muted">
        {ai.model} · {ai.usage.input_tokens.toLocaleString()} tokens in /{' '}
        {ai.usage.output_tokens.toLocaleString()} out
      </p>
      {ai.rejected && (
        <p className="error">
          Rejected by DevAI: {ai.rejected}. Nothing will be changed.
        </p>
      )}
      {task === 'analysis' && <Analysis report={ai.report} />}
      {task === 'review' && <Review report={ai.report} discarded={ai.discarded_issues} />}
      {task === 'docs' && (
        <Proposal
          diff={ai.diff}
          added={ai.added}
          dropped={ai.dropped}
          checked={
            result.docs.file.endsWith('.py')
              ? 'Only documentation changed: checked. Without docstrings, the code parses to exactly the same syntax tree as before.'
              : 'Only documentation changed: checked. Each addition is a single /** */ comment right above an export, with no code in it.'
          }
        />
      )}
      {task === 'readme' && (
        <Proposal
          diff={ai.diff}
          added={ai.added.map((item) => `${item.heading} (${item.topic})`)}
          dropped={ai.dropped.map((item) => ({ name: item.section, reason: item.reason }))}
          links={ai.links}
          leftOut={result.left_out}
          checked={
            ai.creates
              ? 'A new README.md: checked. devai docs finds each section, and every npm command in it runs a script that exists.'
              : 'Only additions: checked. Every line of the README is still there, unchanged and in order, and no new npm command fails.'
          }
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
        <p className="error">Can't offer it as a comment: {result.comment_blocked}.</p>
      )}
      {task === 'tests' && <Tests ai={ai} runCommand={result.run_command} />}
      <List title="Notes from the AI" items={ai.proposal?.notes ?? []} />
      <p className="muted">Written by AI. Read it before applying anything.</p>
    </div>
  );
}

function Analysis({ report }) {
  return (
    <>
      <p>{report.summary}</p>
      <h4>Risks</h4>
      <ul className="list">
        {report.risks.map((risk, index) => (
          <li key={index}>
            <Severity level={risk.severity} /> <strong>{risk.title}</strong>: {risk.explanation}
          </li>
        ))}
      </ul>
      <h4>Recommendations</h4>
      <ol>
        {report.recommendations.map((step, index) => (
          <li key={index}>
            <strong>{step.title}</strong> [{step.effort} effort]: {step.rationale}
          </li>
        ))}
      </ol>
      <List title="Limitations" items={report.limitations} />
    </>
  );
}

function Review({ report, discarded }) {
  return (
    <>
      <p>{report.summary}</p>
      <h4>Issues</h4>
      {report.issues.length === 0 && <p className="muted">None found.</p>}
      <ul className="list">
        {report.issues.map((issue, index) => (
          <li key={index}>
            <Severity level={issue.severity} /> <strong>{issue.title}</strong>{' '}
            <code className="where">
              {issue.file}
              {issue.line ? `:${issue.line}` : ''}
            </code>
            <div>{issue.explanation}</div>
            <div className="muted">Suggestion: {issue.suggestion}</div>
          </li>
        ))}
      </ul>
      {discarded > 0 && (
        <p className="muted">{discarded} issue(s) about code the AI wasn't shown were discarded.</p>
      )}
      <List title="Suggested tests" items={report.suggested_tests} />
      <List title="Limitations" items={report.limitations} />
    </>
  );
}

function Proposal({ diff, added = [], dropped = [], links = [], leftOut = [], checked }) {
  return (
    <>
      {diff ? <Diff text={diff} /> : <p className="muted">No usable change in the answer.</p>}
      {added.length > 0 && <p>Added: {added.join(', ')}</p>}
      {diff && <p className="checked">{checked}</p>}
      <List
        title="Not used"
        items={dropped.map((item) => `${item.name}: ${item.reason}`)}
      />
      <List title="Links the AI wrote (check them)" items={links} />
      <List
        title="Not asked"
        items={leftOut.map((item) => `${item.topic}: ${item.reason}`)}
      />
    </>
  );
}

function Plan({ plan, dropped }) {
  return (
    <>
      <p>{plan.summary}</p>
      <List title="Files to look at" items={plan.files.map((file) => `${file.path}: ${file.why}`)} />
      {dropped > 0 && <p className="muted">{dropped} file(s) the AI wasn't shown were left out.</p>}
      {plan.steps.length > 0 && (
        <>
          <h4>Steps</h4>
          <ol>
            {plan.steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </>
      )}
      <List title="Tests" items={plan.tests} />
      <List title="Open questions" items={plan.questions} />
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
  const paths = Object.keys(diffs ?? {});
  return (
    <>
      <p>{proposal.summary}</p>
      {paths.length === 0 && <p className="muted">No change proposed.</p>}
      {paths.map((path) => (
        <Diff key={path} text={diffs[path]} />
      ))}
      <List title="Risks" items={proposal.risks} />
      <List title="How to verify" items={proposal.tests} />
    </>
  );
}

function Tests({ ai, runCommand }) {
  return (
    <>
      {ai.path && (
        <p>
          New file: <code>{ai.path}</code>
        </p>
      )}
      <pre className="code">{ai.proposal.content}</pre>
      {runCommand && (
        <p>
          Run them yourself with: <code>{runCommand}</code>. DevAI never runs them.
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
