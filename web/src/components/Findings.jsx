/** Findings of the local checks, worst first (the API already sorts them). */
export default function Findings({ findings, passed = [] }) {
  return (
    <div className="findings">
      {findings.length === 0 && <p className="muted">No findings.</p>}
      <ul className="list">
        {findings.map((finding, index) => (
          <li key={index}>
            <Severity level={finding.severity} />
            <span>{finding.message}</span>
            {finding.file && (
              <code className="where">
                {finding.file}
                {finding.line ? `:${finding.line}` : ''}
              </code>
            )}
            {finding.evidence && <code className="evidence">{finding.evidence}</code>}
          </li>
        ))}
      </ul>
      {passed.length > 0 && (
        <ul className="list passed">
          {passed.map((message) => (
            <li key={message}>✓ {message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Severity({ level }) {
  return <span className={`severity severity-${level}`}>{level.toUpperCase()}</span>;
}
