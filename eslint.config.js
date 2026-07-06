// ESLint-konfig för frontendens vanilla JS (globala script, ingen build).
// Fokus: rena korrekthetsregler som fångar buggar — inte stil. Regler som
// kräver kännedom om globals mellan script-taggar (no-undef m.fl.) är
// medvetet avstängda; typkontrollen (npm run typecheck) tar det ansvaret
// i takt med @ts-check-utrullningen.
"use strict";

module.exports = [
  {
    files: ["app/frontend/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2021,
      sourceType: "script",
    },
    rules: {
      "no-compare-neg-zero": "error",
      "no-cond-assign": "error",
      "no-const-assign": "error",
      "no-constant-binary-expression": "error",
      "no-dupe-args": "error",
      "no-dupe-else-if": "error",
      "no-dupe-keys": "error",
      "no-duplicate-case": "error",
      "no-empty-pattern": "error",
      "no-fallthrough": "error",
      "no-func-assign": "error",
      "no-invalid-regexp": "error",
      "no-obj-calls": "error",
      "no-redeclare": "error",
      "no-self-assign": "error",
      "no-self-compare": "error",
      "no-shadow-restricted-names": "error",
      "no-sparse-arrays": "error",
      "no-unreachable": "error",
      "no-unsafe-negation": "error",
      "use-isnan": "error",
      "valid-typeof": "error",
    },
  },
];
