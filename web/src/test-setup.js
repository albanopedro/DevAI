import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Each test starts from an empty page, and no language remembered.
afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
