import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // eslint-plugin-react-hooks' recommended config also enables the
      // React Compiler's static-correctness rules (set-state-in-effect,
      // set-state-in-render, immutability, purity, refs, globals,
      // error-boundaries, config, gating, use-memo,
      // preserve-manual-memoization). Those assume the React Compiler
      // babel transform is running; this project does not use the
      // compiler (no babel-plugin-react-compiler configured), and they
      // flag ordinary, correct patterns used throughout this codebase
      // (effect-based data fetching, syncing local editable state from a
      // prop). Keep the two hook rules that apply regardless of the
      // compiler.
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/set-state-in-render': 'off',
      'react-hooks/immutability': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/globals': 'off',
      'react-hooks/error-boundaries': 'off',
      'react-hooks/config': 'off',
      'react-hooks/gating': 'off',
      'react-hooks/use-memo': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
    },
  },
])
