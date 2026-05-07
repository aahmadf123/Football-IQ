import tseslint from "typescript-eslint";

const eslintConfig = tseslint.config(
  {
    ignores: [".next/**", "out/**", "build/**", "next-env.d.ts"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-unused-vars": "warn",
    },
  },
);

export default eslintConfig;
