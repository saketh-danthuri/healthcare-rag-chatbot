import nextConfig from "eslint-config-next";

const eslintConfig = [
  ...nextConfig,
  {
    ignores: [".next/**", "out/**"],
  },
  {
    // Override overly strict React 19 rules that flag legitimate patterns
    // (e.g., loading from localStorage in useEffect, resetting state on dep change)
    rules: {
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default eslintConfig;
