import js from '@eslint/js'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import hooks from 'eslint-plugin-react-hooks'
import globals from 'globals'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  js.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}', 'tests/**/*.{ts,tsx}', 'vite.config.ts'],
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
      'react-hooks': hooks,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      '@typescript-eslint/no-explicit-any': 'error',
      'no-undef': 'off',
    },
  },
]
