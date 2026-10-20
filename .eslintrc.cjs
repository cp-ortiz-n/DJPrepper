module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
  },
  extends: ['eslint:recommended'],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  rules: {
    // Phase 0 prioritizes runtime correctness. Existing extraction-era dead code is
    // measured separately and will be removed with its owning feature slice.
    'no-unused-vars': 'off',
    'no-constant-condition': 'off',
    'no-empty': 'off',
    'no-useless-catch': 'off',
  },
  overrides: [
    {
      files: [
        'frontend/features/music-files/index.js',
        'frontend/features/dj-library/index.js',
        'frontend/features/settings/index.js',
        'frontend/features/reporting/index.js',
        'frontend/features/set-builder/index.js',
      ],
      rules: {
        'no-restricted-globals': ['error', { name: 'fetch', message: 'Use the injected frontend API service.' }],
      },
    },
    {
      files: ['tests/javascript/**/*.test.js', 'scripts/**/*.mjs'],
      env: { browser: false, node: true },
    },
    {
      files: ['tests/browser/**/*.spec.js'],
      env: { browser: true, node: true },
    },
  ],
};
