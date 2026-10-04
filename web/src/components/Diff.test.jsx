import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import Diff from './Diff.jsx';

test('lines are colored by kind', () => {
  render(<Diff text={'--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n same\n'} />);

  expect(screen.getByText('-old').className).toBe('diff-remove');
  expect(screen.getByText('+new').className).toBe('diff-add');
  expect(screen.getByText('@@ -1 +1 @@').className).toBe('diff-hunk');
  expect(screen.getByText('--- a/x').className).toBe('diff-file');
});

test('HTML in a diff is shown as text, never run', () => {
  const { container } = render(<Diff text={'+<script>alert(1)</script>\n+<img src=x onerror=alert(1)>\n'} />);

  expect(container.querySelector('script')).toBeNull();
  expect(container.querySelector('img')).toBeNull();
  expect(screen.getByText('+<script>alert(1)</script>')).toBeTruthy();
});
