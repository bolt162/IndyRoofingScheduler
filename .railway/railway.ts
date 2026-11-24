import { defineRailway, github, project, service } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "scheduler";
export default defineRailway(() => {
  const scheduler = service("scheduler", {
    source: github("bolt162/IndyRoofingScheduler", { branch: "main", checkSuites: false }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "./Dockerfile" },
    healthcheck: "/api/health",
    healthcheckTimeout: 120,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyMaxRetries: 3 },
    domains: ["indyscheduler.top"],
  });

  return project("content-strength", {
    variables: { managed: false },
    resources: [scheduler],
  });
});
