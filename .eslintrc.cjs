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
      files: ['tests/*.test.js', 'scripts/*.mjs'],
      env: { browser: false, node: true },
    },
  ],
};
