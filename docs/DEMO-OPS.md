# Demo operations

Public demo API: `https://anyq-demo-api.onrender.com`. Public demo web: `https://anyq-demo.vercel.app`.

`.github/workflows/demo-keepwarm.yml` reads those origins from the repository variables `DEMO_API_URL` and `DEMO_WEB_URL`. The variables are not secrets. An empty variable falls back to the public origin above.

Scheduled workflows run only from the default branch: this file must be on main.

## Render hours

One always-on service is 744 h of 750 h/month. This window is ~370 h. Any other free service in the same Render workspace shares the pool.

Actions usage (~2 200 short runs/month) is free while public. If the repo becomes private the 2 000 min/month free quota would be exceeded, so shrink the window.

## Schedule

The workflow runs every 10 minutes from 08:00 through 21:59 Asia/Almaty, Monday through Saturday. The cron is `*/10 3-16 * * 1-6`. GitHub cron is UTC, best-effort and may be delayed or skipped.

Each run requests API `/healthz` and web `/ru` and expects HTTP 200. `/healthz` uses curl `--max-time 45` with 3 retries, inside a 200 second limit, so a slow attempt still leaves time for the retries.

`workflow_dispatch` starts the same checks from the Actions tab. The input `check_content` is a boolean. It stays off unless the operator sets it.

Render keeps the service ~15 min after the window.

## Content checks

Content checks run only when the repository variable `DEMO_CHECK_CONTENT` is `true` or the `check_content` input is set. They depend on separate pull requests, so they are off by default.

Enable DEMO_CHECK_CONTENT=true only after REGISTRATION_ENABLED is merged, otherwise it would create real accounts every 10 min.

When they run:

- web `/ru` contains `ДЕМО`
- `POST /v1/auth/register` with a random `@example.com` e-mail is rejected (non-2xx). The address and password are generated for that run and are not stored in the repository.
- a request with `Origin: https://example.org` gets no `Access-Control-Allow-Origin`
- `/docs` returns 404

## How to read alerts

Alerts are an e-mail and an issue.

The job fails, so GitHub sends its workflow-failure e-mail. The GitHub scheduled workflow goes to whoever last changed the cron (the owner merges it, so alerts go to them). GitHub emails failures to whoever last changed the cron, so the owner should Watch the repo. GitHub disables schedules after 60 days without activity.

The run opens or updates a single issue with the label `demo-alert`, created by `github-actions[bot]`, titled `Demo down`. The workflow finds that issue by the label and the creator. The issue includes the failing check and the run URL. A comment is added when a closed issue is opened again or the failing check changes. On success the workflow closes that issue if it is open.

## Manual warm-up

Warm the demo 10 min before a show. Run this workflow from the Actions tab, or open API `/healthz` and web `/ru`, and wait until both return HTTP 200. Render Free sleeps after 15 minutes of idle time, and a cold start takes 50–90 seconds.

## Rollback

Roll back with Render rollback, Vercel instant rollback, or a `git revert` pull request into `demo`.

## CI

Pull requests into `demo` run `.github/workflows/ci.yml`. Its `pull_request` trigger has no base-branch filter, so `demo` is already included.
