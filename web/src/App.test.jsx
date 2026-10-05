import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import App, { shortPath } from './App.jsx';

test('without the token, the page says how to open it', () => {
  render(<App token={null} />);

  expect(screen.getByText(/the address/)).toBeTruthy();
  expect(screen.getByText('devai serve')).toBeTruthy();
});

test('long paths are shortened to their last two folders', () => {
  expect(shortPath('/Users/someone/code/projects/bookshelf')).toBe('…/projects/bookshelf');
  expect(shortPath('/srv/app')).toBe('/srv/app');
});

test('EN | PT switches the page, and the browser remembers it', () => {
  render(<App token={null} />);
  expect(screen.getByText(/carries the key/)).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'Português' }));

  expect(screen.getByText(/traz a chave/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Português' }).getAttribute('aria-pressed')).toBe('true');
  expect(document.documentElement.lang).toBe('pt-BR');
  expect(window.localStorage.getItem('devai-language')).toBe('pt');
});

test('a language chosen before is used at start', () => {
  window.localStorage.setItem('devai-language', 'pt');

  render(<App token={null} />);

  expect(screen.getByText(/Abra esta página/)).toBeTruthy();
});
