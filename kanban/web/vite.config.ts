import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { precompress } from './build/precompress.ts';

export default defineConfig({
  plugins: [react(), precompress()],
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
  },
});
