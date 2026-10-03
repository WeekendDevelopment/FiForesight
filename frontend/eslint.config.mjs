import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import eslintNextPlugin from '@next/eslint-plugin-next'

const eslintConfig = defineConfig([
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    plugins: {
      next: eslintNextPlugin
    },
    rules: {
      ...eslintNextPlugin.configs.recommended.rules,
    },
  },
  ...nextVitals,
  // eslint-config-next >=16.3 bundles eslint-plugin-react-hooks v7, which enables
  // the React Compiler rules below as errors. This codebase fetches data inside
  // effects — an idiomatic pattern these rules flag across ~15 components — so they
  // are deferred to a dedicated refactor rather than blocking upstream bumps.
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    rules: {
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    '.next/**',
    'out/**',
    'build/**',
    'next-env.d.ts',
  ]),
])

export default eslintConfig