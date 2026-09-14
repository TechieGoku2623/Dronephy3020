# GridOS SaaS Release Checklist

## Security
- [ ] Set `GRIDOS_REQUIRE_API_KEY=true`
- [ ] Set strong tokens via `GRIDOS_API_KEYS`
- [ ] Set `GRIDOS_ENFORCE_TENANT_HEADER=true`
- [ ] Restrict `GRIDOS_CORS_ORIGINS` to production domain(s)
- [ ] Run `python3 scripts/validate_production_env.py --env-file .env`

## Reliability
- [ ] Configure `GRIDOS_RATE_LIMIT_PER_MINUTE` for expected load
- [ ] Verify `/health/live` and `/health/ready` probes
- [ ] Enable centralized log collection for request ID tracing

## Deployment
- [ ] Generate env file with `python3 scripts/generate_production_env.py --domain app.<your-domain> --output .env`
- [ ] Run `docker compose up --build`
- [ ] Confirm API on port `8000` and UI on port `3000`

## Validation
- [ ] `python3 -m pytest -q` passes
- [ ] `npm run build` succeeds
- [ ] Confirm tenant isolation by testing two distinct `X-Tenant-ID` values
- [ ] Confirm unauthenticated requests fail when API key requirement is enabled
