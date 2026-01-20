import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./unit/setup.js'],
    include: ['unit/**/*.test.js'],
    exclude: ['e2e/**', 'node_modules/**'],
    coverage: {
      reporter: ['text', 'html'],
      include: ['../../powder/web/js/**/*.js'],
      thresholds: {
        statements: 75,
        branches: 75,
        functions: 75,
        lines: 75,
      },
    },
  },
});
