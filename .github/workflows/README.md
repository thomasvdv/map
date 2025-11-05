# GitHub Actions Workflows

This directory contains automated workflows for maintaining the OLC flight map.

## Workflows

### 1. Daily Update (`daily-update.yml`)

**Purpose**: Automatically check for new flights daily and update the map on Cloudflare R2.

**Schedule**: Runs daily at 2:00 AM UTC

**What it does**:
1. Downloads existing flight metadata from R2
2. Checks OLC for new flights at the configured airport
3. Downloads any new IGC files (respects OLC's 20/day limit)
4. Generates satellite tiles for new flight dates (optional)
5. Regenerates the interactive map with all flights
6. Uploads only new/changed files to R2 (smart deduplication)

**Manual trigger**: You can also trigger this workflow manually from the GitHub Actions tab with custom parameters:
- Airport code (default: STERL1)
- Skip satellite tiles option

**Requirements**: See "Required Secrets" section below.

---

### 2. Manual Update (`manual-update.yml`)

**Purpose**: On-demand map generation with full control over parameters.

**Trigger**: Manual only (via GitHub Actions UI)

**Parameters**:
- **Airport code**: Which airport to process (e.g., STERL1)
- **Year**: Optional - process only a specific year
- **Min points**: Optional - filter flights by minimum points
- **Skip download**: Use existing data from R2 instead of downloading new flights
- **Skip satellite tiles**: Skip satellite tile generation (faster)
- **Force regenerate**: Ignore deduplication, regenerate everything

**Use cases**:
- Initial setup of a new airport
- Regenerating map after configuration changes
- Testing changes before committing to daily automation
- Recovering from failed daily runs

---

## Required GitHub Secrets

To use these workflows, you must configure the following secrets in your repository:

**GitHub Repository Settings → Secrets and variables → Actions → New repository secret**

### OLC Credentials
- `OLC_USERNAME`: Your OnlineContest.org account username
- `OLC_PASSWORD`: Your OnlineContest.org account password

### Cloudflare R2 Credentials
- `R2_ACCOUNT_ID`: Your Cloudflare account ID (found in R2 dashboard URL)
- `R2_ACCESS_KEY_ID`: R2 API access key ID
- `R2_SECRET_ACCESS_KEY`: R2 API secret access key
- `R2_PUBLIC_DOMAIN`: (Optional) Custom R2 public domain
  - If not set, defaults to: `pub-32af5705466c411d82c79b436565f4a9.r2.dev`

**How to create R2 API tokens**:
1. Go to Cloudflare Dashboard → R2 → Overview
2. Click "Manage R2 API Tokens"
3. Click "Create API Token"
4. Give it a name (e.g., "GitHub Actions")
5. Permissions: Object Read & Write
6. Copy the Access Key ID and Secret Access Key
7. Add them to GitHub Secrets

---

## How It Works

### Stateless Design

The workflows are designed to run in stateless CI/CD environments:

1. **Download phase**: Retrieve necessary data from R2
   - Flight metadata (JSON files tracking what exists)
   - Recent flight IGC files (last 30 days) for context
   - VFR tiles stay in R2 (too large to download each run)

2. **Processing phase**: Generate new content
   - Check OLC for new flights
   - Download new IGC files
   - Generate satellite tiles for new dates
   - Regenerate map HTML with all flights

3. **Upload phase**: Sync changes back to R2
   - Only uploads new/changed files (MD5 checksum comparison)
   - Skips VFR tiles (unchanged)
   - Updates maps, metadata, and new flight files

### Deduplication

All uploads use smart deduplication:
- Compares MD5 checksums before uploading
- Skips files that already exist with same content
- Dramatically reduces upload time and bandwidth

**Example**: If only 3 new flights were added:
- Old way: Re-upload everything (~6 GB, 30-60 minutes)
- New way: Upload only new files (~500 KB, 10-30 seconds)

---

## Monitoring

### Viewing workflow runs

1. Go to your repository on GitHub
2. Click the "Actions" tab
3. Click on a workflow run to see details
4. Click on "update-flights" job to see logs

### Logs and artifacts

Each workflow run saves logs and outputs as artifacts:
- Retained for 7 days (daily runs) or 30 days (manual runs)
- Download from the workflow run page
- Includes:
  - Scrapy logs
  - Processing logs
  - Update summary
  - Generated HTML files (manual runs only)

### Notifications

Failed workflow runs will:
- Appear in the Actions tab with a red ❌
- Send email notifications (if enabled in GitHub settings)
- Show errors in the workflow logs

---

## Cost Analysis

### GitHub Actions (FREE)

**Free tier**:
- 2,000 minutes/month for private repositories
- Unlimited for public repositories

**Usage**:
- Daily run: ~10-15 minutes
- Monthly: ~300-450 minutes
- **Well within free tier limits** ✅

### Cloudflare R2 (FREE)

**Free tier**:
- 10 GB storage (free forever)
- 10 GB/month egress (downloads)
- Unlimited ingest (uploads)
- 1 million Class A operations/month (PUT, LIST)
- 10 million Class B operations/month (GET)

**Estimated usage**:
- Storage: ~6-10 GB (one airport, 15 years of flights + tiles)
- Daily egress: ~50 MB (metadata + recent flights download)
- Monthly egress: ~1.5 GB
- **Well within free tier limits** ✅

**Cost if you exceed free tier**:
- Storage: $0.015/GB/month (after 10 GB)
- Egress: $0.36/TB (after 10 GB/month)

---

## Troubleshooting

### "Worker exceeded CPU time limit"
- You're not using Cloudflare Workers, ignore this

### "OLC authentication failed"
- Check OLC_USERNAME and OLC_PASSWORD secrets
- Verify credentials work by logging into OLC website manually

### "R2 upload failed"
- Check R2 credentials are correct
- Verify R2 bucket exists and is named "map"
- Check R2 API token has Read & Write permissions

### "No new flights found"
- This is normal if no pilots flew that day
- Check workflow logs to verify OLC scraping worked
- Manual trigger with `--force` to regenerate anyway

### "Playwright browser not found"
- The workflow installs browsers automatically
- If it fails, check the "Install Playwright browsers" step logs

### Daily workflow not running
- Check the cron schedule in `daily-update.yml`
- GitHub Actions schedules can have up to 15-minute delays
- Verify the workflow file is in the default branch (main/master)
- Repository must have at least one commit after adding the workflow

---

## Customization

### Change the schedule

Edit `.github/workflows/daily-update.yml`:

```yaml
on:
  schedule:
    - cron: '0 2 * * *'  # Change this line
```

Cron syntax:
- `0 2 * * *` = 2:00 AM UTC daily
- `0 */6 * * *` = Every 6 hours
- `0 0 * * 0` = Weekly on Sunday at midnight

Use [crontab.guru](https://crontab.guru) to build cron expressions.

### Change the airport

Edit the `AIRPORT_CODE` in the workflow or pass it as a parameter when manually triggering.

### Skip satellite tiles

Satellite tiles add 5-15 minutes to runtime. To skip:
- Edit workflow and add `skip_satellite_tiles: true` to daily-update.yml
- Or pass `--skip-satellite-tiles` when manually triggering

### Add multiple airports

To monitor multiple airports:
1. Create separate workflow files for each airport
2. Or modify `daily-update.yml` to loop through multiple airports
3. Be mindful of OLC's 20 downloads/day limit

---

## Migration from Local Setup

If you're migrating from running locally:

1. **Initial upload**: Run manual update once with all flights
   ```bash
   # Locally, upload everything to R2
   python -m olc_downloader.cli upload-to-r2 --all
   ```

2. **Enable workflows**: Commit and push workflow files

3. **Add secrets**: Configure all required secrets in GitHub

4. **Test**: Manually trigger `manual-update.yml` to verify everything works

5. **Daily automation**: Let `daily-update.yml` take over daily updates

---

## Support

For issues or questions:
- Check workflow logs in GitHub Actions tab
- Review this documentation
- Open an issue in the repository
- Check Cloudflare R2 dashboard for storage usage

---

## Architecture Diagram

```
┌─────────────────┐
│  GitHub Actions │
│   (Free CI/CD)  │
└────────┬────────┘
         │
         ├─ Every day at 2 AM UTC
         │
         v
┌─────────────────┐     ┌──────────────┐
│ 1. Download     │────▶│ Cloudflare   │
│    metadata     │◀────│ R2 Storage   │
│    from R2      │     │              │
└────────┬────────┘     │ - Flight IGC │
         │              │ - Metadata   │
         v              │ - VFR tiles  │
┌─────────────────┐     │ - Sat tiles  │
│ 2. Check OLC    │     │ - Maps       │
│    for new      │     └──────────────┘
│    flights      │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ 3. Download     │
│    new IGC      │
│    files        │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ 4. Generate     │
│    satellite    │
│    tiles        │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ 5. Regenerate   │
│    map HTML     │
└────────┬────────┘
         │
         v
┌─────────────────┐     ┌──────────────┐
│ 6. Upload only  │────▶│ Cloudflare   │
│    new/changed  │     │ R2 Storage   │
│    files to R2  │     │              │
└─────────────────┘     └──────────────┘
                               │
                               v
                        ┌──────────────┐
                        │ Public URL   │
                        │ Served to    │
                        │ Users        │
                        └──────────────┘
```

---

**Last updated**: 2025-01-05
