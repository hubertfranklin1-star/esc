# RCA — Redeploy blocked (deployment_blocked / phishing classification)

## Summary
The redeploy cannot proceed because the deployment has been **blocked at the platform level by the phishing/abuse classifier**. This is not a build, source, manifest, secret, tier, or database problem. No code or configuration change on the app can clear it.

## Evidence
1. **Current committed run — `trigger_indie` failed with HTTP 409:**
   ```
   deployer indie returned status 409:
   {"code":"deployment_blocked","error":"This deployment was blocked. If you believe this is a mistake, please contact support."}
   (type: deployer_indie_4xx, retryable: false)
   ```
   Marked `retryable: false`.

2. **Prior run `2bfcea6e-a0a5-47ae-9bb9-b3b87edbe584` failed at the `await_phishing` step:**
   ```
   await_phishing: ... AwaitPhishingClassification ...
   deployment blocked: there has been an error with this deployment.
   Please fork the session and start a new deployment
   ```
   `get_step_status` shows every downstream step (mongodb_migrate, manage_secrets, deploy, health_check) as "not run: an earlier deploy step failed" — the pipeline never got past the phishing gate.

3. Deployment currently has custom domains `tsxtrust.net` and `www.tsxtrust.net` (both verified). The last **successful** run (`57d27157`) is still active and serving `https://upgrade-build-1.emergent.host` — i.e. the previously-live version is unaffected; only the new redeploy is blocked.

## Root Cause
The deployment was flagged and blocked by the automated phishing/abuse classification gate (`await_phishing`). Subsequent deploy triggers now return `409 deployment_blocked`. This is a platform-enforced block and is non-retryable from the pipeline.

## Why resume_pipeline was not fired
The 409 is explicitly non-retryable and originates from the platform block, not the run itself. Re-firing would deterministically return the same `deployment_blocked` 409 without making progress.

## Required Action
- This block can only be lifted by Emergent (platform/trust-and-safety). The block message itself instructs: *"If you believe this is a mistake, please contact support."*
- The user should file an Emergent support ticket quoting deployment_id `b08e2cdb-7a5f-455c-91ab-b6afce3bb0e1` and job_id `9ad74ab5-1fa8-474c-854e-0f1130512359`, asking for a review/unblock of the deployment flagged by the phishing classifier. Alternatively, as the pipeline message suggests, fork the session and start a new deployment.
- No app-side change (code, manifest, secret, tier, DB) will clear this.
