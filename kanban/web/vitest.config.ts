import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    // Coverage instrumentation on a shared CI runner makes the heaviest jsdom route tests
    // exceed the 5s default (observed 5.1s alone, 13s under load); 30s avoids flaky reds.
    testTimeout: 30000,
    include: [
      'src/**/*.{test,spec}.{ts,tsx}',
      'build/**/*.{test,spec}.ts',
      'e2e/support/**/*.unit.test.ts',
    ],
    coverage: {
      provider: 'v8',
      include: process.env.COVERAGE_INCLUDE
        ? process.env.COVERAGE_INCLUDE.split(',')
        : ['src/**/*.{ts,tsx}', 'build/**/*.ts', 'e2e/support/**/*.ts'],
      exclude: [
        'src/main.tsx',
        '**/*.test.*',
        '**/*.spec.*',
        'src/api/schema.gen.ts',
        '**/*.gen.ts',
        '**/*.css',
      ],
      thresholds: {
        lines: 95,
        functions: 95,
        branches: 95,
        statements: 95,
      },
    },
  },
});
