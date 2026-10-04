import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import App from './App.jsx';

test('without the token, the page says how to open it', () => {
  render(<App token={null} />);

  expect(screen.getByText(/the address/)).toBeTruthy();
  expect(screen.getByText('devai serve')).toBeTruthy();
});
