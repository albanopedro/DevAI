/** A unified diff, line by line, always as plain text: never as HTML. */
export default function Diff({ text }) {
  const lines = text.replace(/\n$/, '').split('\n');
  return (
    <pre className="diff" aria-label="diff">
      {lines.map((line, index) => (
        <span key={index} className={lineClass(line)}>
          {line}
          {'\n'}
        </span>
      ))}
    </pre>
  );
}

function lineClass(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'diff-file';
  if (line.startsWith('@@')) return 'diff-hunk';
  if (line.startsWith('+')) return 'diff-add';
  if (line.startsWith('-')) return 'diff-remove';
  return undefined;
}
