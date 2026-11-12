import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

export default tseslint.config(
  {
    ignores: ['dist/**', 'coverage/**', 'node_modules/**'],
  },
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: {
          allowDefaultProject: ['./eslint.config.js'],
          defaultProject: 'tsconfig.json',
        },
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  {
    files: ['**/*.js', '**/*.mjs'],
    ...tseslint.configs.disableTypeChecked,
  },
  reactHooks.configs.flat.recommended,
  {
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'styled-components',
              message: 'Runtime CSS-in-JS is banned per S2.5; use static CSS.',
            },
            {
              name: 'next',
              message: 'Next.js is banned per S2.5; use Vite SPA.',
            },
          ],
          patterns: [
            {
              group: ['@emotion/*'],
              message: 'Runtime CSS-in-JS is banned per S2.5; use static CSS.',
            },
            {
              group: ['@tiptap-pro/*'],
              message: 'Proprietary @tiptap-pro/* is banned per S2.5.',
            },
          ],
        },
      ],
    },
  },
);
