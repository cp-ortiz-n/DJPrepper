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
        'web/features/music-files/index.js',
        'web/features/dj-library/index.js',
        'web/features/settings/index.js',
        'web/features/reporting/index.js',
        'web/features/set-builder/index.js',
      ],
      rules: {
        'no-restricted-globals': ['error', { name: 'fetch', message: 'Use the injected frontend API service.' }],
      },
    },
    {
      files: ['tests/javascript/**/*.test.js', 'scripts/*.mjs'],
      env: { browser: false, node: true },
    },
    {
      files: ['tests/browser/**/*.spec.js'],
      env: { browser: true, node: true },
    },
  ],
};
