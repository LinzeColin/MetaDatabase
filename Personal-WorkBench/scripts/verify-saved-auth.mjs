import { writeFile } from "node:fs/promises";

/**
 * A Saved Candidate is intentionally not invented from the local preview. The
 * future operator can set a non-secret HTTPS origin and extend this probe after
 * actual Google, mail, and Turnstile materials have been configured.
 */
const origin = process.env.SITES_SAVED_AUTH_ORIGIN;
const report = {
  stage: "S2",
  status: origin ? "NOT_IMPLEMENTED_SAVED_CANDIDATE_PROBE" : "NOT_RUN",
  savedCandidate: "NOT_RUN",
  reason: "No Saved Candidate auth origin was supplied; no external account or provider flow was attempted.",
};
await writeFile("13_evidence/auth-saved.json", `${JSON.stringify(report, null, 2)}\n`);
process.stdout.write(`${report.status}\n`);
