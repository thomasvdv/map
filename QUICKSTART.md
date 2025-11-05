# Quick Start Guide

## Testing with Your OLC Account

Now that the package is installed, follow these steps to download your IGC files:

### Step 1: Configure Your Credentials

```bash
olc-download configure
```

You'll be prompted to enter your OLC username and password. These will be securely stored in `~/.olc-downloader/config.env`.

### Step 2: Verify Your Setup

Check what years are available:

```bash
olc-download list-years
```

This will log in and show you all years where you have flights.

### Step 3: Preview Your Flights

See what flights are available (optional):

```bash
olc-download list-flights
```

Or for a specific year:

```bash
olc-download list-flights --year 2024
```

### Step 4: Download Your Files

#### Dry Run First (Recommended)

See what would be downloaded without actually downloading:

```bash
olc-download download --dry-run
```

#### Download Everything

Download all IGC files from all years:

```bash
olc-download download
```

Files will be saved to `./downloads/` organized by year.

#### Download Specific Year

```bash
olc-download download --year 2024
```

#### Custom Output Directory

```bash
olc-download download --output ~/my-igc-backup
```

### Step 5: Re-download if Needed

If you need to re-download files (e.g., interrupted download):

```bash
olc-download download --force
```

## Troubleshooting

### Login Issues

If you get authentication errors:

1. Verify your credentials work on the OLC website first
2. Reconfigure: `olc-download configure`
3. Try with verbose logging: `olc-download download --verbose`

### The scraper might need adjustment

The scraper module makes assumptions about the OLC website structure. If it doesn't find your flights:

1. Run with `--verbose` to see detailed logs
2. Check `src/olc_downloader/scraper.py` - you may need to adjust:
   - URL patterns for accessing flight history
   - HTML selectors for finding IGC links
   - Date extraction patterns

### Check the actual OLC website structure

To debug issues, you can:

1. Log in to OLC manually
2. Navigate to your flight history
3. Inspect the HTML to find:
   - The correct URL for flight history
   - How IGC download links are structured
   - How years and dates are displayed

Then update `scraper.py` accordingly.

## Next Steps

Once you've successfully downloaded your flights:

1. **Verify the downloads**: Check that IGC files are valid
2. **Backup to multiple locations**: Consider cloud storage, external drives
3. **Test opening files**: Use an IGC viewer to verify file integrity

## Important Reminder

⚠️ **OLC is shutting down September 22, 2025!** Make sure to download your flight data before then.

## Common Commands Summary

```bash
# Configure credentials
olc-download configure

# List available years
olc-download list-years

# List all flights
olc-download list-flights

# Download all flights (dry run)
olc-download download --dry-run

# Download all flights
olc-download download

# Download specific year
olc-download download --year 2024

# Download with custom output
olc-download download --output ~/backup

# Force re-download
olc-download download --force

# Verbose mode for debugging
olc-download download --verbose
```
