import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { precompress } from './build/precompress.ts';
import { PRODUCTION_CSP } from './e2e/support/csp.ts';

export default defineConfig({
  plugins: [react(), precompress()],
  worker: {
    format: 'es',
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
  },
  preview: {
    headers: {
      'Content-Security-Policy': PRODUCTION_CSP,
    },
  },
});
