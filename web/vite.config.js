import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// `npm run build` writes the pages to dist/, which `devai serve` serves.
// `npm run dev` serves them with hot reload and forwards /api to a running
// `devai serve` (port 8765); open the dev page with the same ?token=.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        // The API accepts only its own origin. In development the page comes
        // from another port, so the proxy drops the header.
        configure: (proxy) => proxy.on('proxyReq', (request) => request.removeHeader('origin')),
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.js'],
  },
});
