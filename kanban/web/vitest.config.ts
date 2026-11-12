import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: [
      'src/**/*.{test,spec}.{ts,tsx}',
      'build/**/*.{test,spec}.ts',
      'e2e/support/**/*.unit.test.ts',
    ],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}', 'build/**/*.ts', 'e2e/support/**/*.ts'],
      exclude: ['src/main.tsx', '**/*.test.*', '**/*.spec.*', 'src/api/schema.gen.ts', '**/*.gen.ts'],
      thresholds: {
        lines: 95,
        functions: 95,
        branches: 95,
        statements: 95,
      },
    },
  },
});
