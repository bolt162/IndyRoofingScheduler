import { defineRailway, github, project, service } from "railway/iac";
// This repository manages only its own service in the project; other repositories
// export their own partial name. See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "scheduler";
export default defineRailway(() => {
  // Same settings as railway.toml, which Railway stops reading on 2026-12-01
  const scheduler = service("scheduler", {
    // Keeps the GitHub hookup: a push to main deploys
    source: github("bolt162/IndyRoofingScheduler"),
    build: { builder: "DOCKERFILE", dockerfilePath: "./Dockerfile" },
    // No build args needed: Railway hands the service's VITE_* variables to the Dockerfile's ARG lines itself
    deploy: {
      healthcheckPath: "/api/health",
      healthcheckTimeout: 120,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 3,
    },
  });

  return project("content-strength", {
    variables: { managed: false },
    resources: [scheduler],
  });
});
