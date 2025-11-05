# OLC Downloader

A full-featured CLI tool to download all your IGC flight files from [onlinecontest.org](https://www.onlinecontest.org/).

⚠️ **Important Notes**:
- **Rate Limit**: OLC limits downloads to 20 IGC files per day per user to prevent mass scraping
- **Good News**: The OLC platform shutdown has been cancelled and will continue operating beyond September 2025!
- **Year Range**: This tool automatically crawls all years from 2007 through 2026
- **Server Issues**: The OLC server can be slow or timeout. The tool includes retry logic and timeout handling

## Features

- 🔐 Secure credential management
- 📅 Download flights from all available years
- 📊 Beautiful progress bars and terminal UI
- 🗂️ Organized downloads by year folders
- 🔄 Resume capability (skips already downloaded files)
- 🎯 Selective download by year
- 🔍 List available years and flights
- 🚀 Fast concurrent downloads
- ✅ IGC file validation
- 🌍 Download public flights from any airport (all pilots)
- 🗺️ Generate interactive maps of flight tracks
- 🧹 Cleanup tools for invalid downloads
- 📊 Filter flights by airport, points, or year

## Two Modes of Operation

This tool supports two distinct modes:

### 1. Personal Flight Mode (Default)
Download and list **your own flights** only:
- Use basic commands without `--all-pilots` flag
- Filter by `--airport` (name) or `--min-points`
- Example: `olc-download download --airport "Staufen" --min-points 100`

### 2. Public Flight Mode
Download and list **all pilots' flights** from a specific airport:
- Requires `--airport-code` (OLC code like STAUB1) and `--all-pilots` flag
- Filter by `--min-points` or `--year`
- Example: `olc-download download --airport-code STAUB1 --all-pilots --min-points 50`
- Note: Cannot combine `--airport` and `--all-pilots` (use `--airport-code` for public mode)

## Installation

### Using pip (recommended)

```bash
# Clone the repository
git clone <repository-url>
cd olc-weglide

# Install in development mode
pip install -e .
```

### Using virtual environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install package
pip install -e .
```

## Quick Start

### 1. Configure your credentials

```bash
olc-download configure
```

You'll be prompted for your OLC username and password. Credentials are stored securely in `~/.olc-downloader/config.env`.

### 2. Download all your flights

```bash
olc-download download
```

This will download all IGC files from all available years to `./downloads/` organized by year.

## Usage

### Configure credentials

```bash
olc-download configure
# Or with inline credentials (not recommended for security):
olc-download configure -u your_username -p your_password
```

### List available years

```bash
olc-download list-years
```

### List all flights

```bash
# List all your personal flights
olc-download list-flights

# List flights for specific year
olc-download list-flights --year 2024

# Filter your personal flights by airport name
olc-download list-flights --airport "Staufen"

# Filter your personal flights by minimum points
olc-download list-flights --min-points 100

# List ALL pilots' public flights from a specific airport
olc-download list-flights --airport-code STAUB1 --all-pilots

# Combine filters for public flights
olc-download list-flights --airport-code STAUB1 --all-pilots --min-points 50 --year 2024
```

### Download flights

```bash
# Download all flights from all years
olc-download download

# Download specific year only
olc-download download --year 2024

# Custom output directory
olc-download download --output /path/to/backup

# Re-download existing files
olc-download download --force

# Dry run (see what would be downloaded)
olc-download download --dry-run

# Verbose output for debugging
olc-download download --verbose

# Download with custom retry attempts
olc-download download --retries 5

# Filter your personal flights by airport name
olc-download download --airport "Staufen"

# Filter your personal flights by minimum points
olc-download download --min-points 100

# Download ALL pilots' public flights from a specific airport
olc-download download --airport-code STAUB1 --all-pilots

# Combine filters for public flights
olc-download download --airport-code STAUB1 --all-pilots --min-points 50 --year 2024
```

### Command Reference

| Command | Description |
|---------|-------------|
| `configure` | Set up OLC credentials |
| `list-years` | List available years with flights |
| `list-flights` | List all available flights (yours or public) |
| `download` | Download IGC files (yours or public) |
| `map` | Generate interactive map of flight tracks for an airport |
| `cleanup` | Remove invalid HTML files from downloads directory |
| `regenerate-metadata` | Regenerate metadata for flights missing it |

### Download Options

| Option | Short | Description |
|--------|-------|-------------|
| `--year` | `-y` | Download only specific year |
| `--output` | `-o` | Output directory (default: ./downloads) |
| `--force` | `-f` | Re-download existing files |
| `--dry-run` | `-n` | Show what would be downloaded |
| `--retries` | `-r` | Number of retry attempts for failed downloads (default: 3) |
| `--airport` | `-a` | Filter by airport name (exact match, case-insensitive) - for YOUR flights only |
| `--airport-code` | | OLC airport code (e.g., STAUB1) - downloads ALL pilots' flights. Requires --all-pilots |
| `--all-pilots` | | Download public flights from ALL pilots (requires --airport-code) |
| `--min-points` | `-p` | Filter by minimum points score |
| `--verbose` | `-v` | Verbose output |

### Generate interactive map

Create an interactive map visualization of flight tracks for a specific airport:

```bash
# Generate map for an airport
olc-download map --airport-code STAUB1

# Limit number of tracks displayed
olc-download map --airport-code STAUB1 --max-tracks 50

# Custom output directory
olc-download map --airport-code STAUB1 --output /path/to/downloads
```

**Map Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--airport-code` | `-a` | Airport code (required, e.g., STERL1) |
| `--output` | `-o` | Output directory (default: ./downloads) |
| `--max-tracks` | `-m` | Maximum number of tracks to display (default: all) |
| `--verbose` | `-v` | Verbose output |

### Cleanup invalid files

Remove invalid HTML files from your downloads directory (useful if some downloads failed):

```bash
# Dry run to see what would be deleted
olc-download cleanup --dry-run

# Delete invalid files
olc-download cleanup

# Custom output directory
olc-download cleanup --output /path/to/downloads
```

**Cleanup Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output directory (default: ./downloads) |
| `--dry-run` | `-n` | Show what would be deleted without deleting |
| `--verbose` | `-v` | Verbose output |

### Regenerate metadata

Regenerate metadata for flights that are missing it (useful after manual file operations):

```bash
# Dry run to see what would be regenerated
olc-download regenerate-metadata --airport-code STAUB1 --dry-run

# Regenerate metadata
olc-download regenerate-metadata --airport-code STAUB1

# With minimum points filter (match your original download filter)
olc-download regenerate-metadata --airport-code STAUB1 --min-points 50

# Custom output directory
olc-download regenerate-metadata --airport-code STAUB1 --output-dir /path/to/downloads
```

**Regenerate Metadata Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--airport-code` | `-a` | Airport code (required, e.g., STERL1) |
| `--output-dir` | `-o` | Output directory (default: downloads) |
| `--min-points` | `-p` | Minimum points filter (use same value as original download) |
| `--dry-run` | | Show what would be done without actually doing it |
| `--verbose` | `-v` | Verbose output |

## Automated Daily Updates (GitHub Actions)

You can set up **completely free automated daily updates** using GitHub Actions and Cloudflare R2:

### Features
- ✅ **100% Free** - Uses GitHub's free CI/CD (2,000 minutes/month)
- ✅ **Automatic scheduling** - Runs daily to check for new flights
- ✅ **Smart deduplication** - Only uploads changed files
- ✅ **Cloudflare R2 integration** - All data stored in R2 (10 GB free)
- ✅ **No server needed** - Runs in the cloud
- ✅ **Manual triggers** - On-demand map regeneration

### Quick Setup

1. **Configure GitHub Secrets** (Repository Settings → Secrets and variables → Actions):
   - `OLC_USERNAME` - Your OLC account username
   - `OLC_PASSWORD` - Your OLC account password
   - `R2_ACCOUNT_ID` - Cloudflare account ID
   - `R2_ACCESS_KEY_ID` - R2 API access key
   - `R2_SECRET_ACCESS_KEY` - R2 API secret key
   - `R2_PUBLIC_DOMAIN` - (Optional) Custom R2 domain

2. **Initial upload** - Run once locally to upload existing data:
   ```bash
   python -m olc_downloader.cli upload-to-r2 --all
   ```

3. **Enable workflows** - Push the workflow files to your repository:
   - `.github/workflows/daily-update.yml` - Runs daily at 2 AM UTC
   - `.github/workflows/manual-update.yml` - Manual trigger option

4. **Done!** - GitHub Actions will now:
   - Check OLC daily for new flights
   - Download new IGC files (respects 20/day limit)
   - Generate satellite tiles for new dates
   - Regenerate interactive map
   - Upload only changed files to R2

### Manual Trigger

You can also trigger updates manually from GitHub:
1. Go to Actions tab in your repository
2. Select "Manual Map Update" workflow
3. Click "Run workflow"
4. Set parameters (airport, year, filters, etc.)

### Documentation

See [.github/workflows/README.md](.github/workflows/README.md) for detailed documentation including:
- How workflows work
- Cost analysis (spoiler: it's free!)
- Monitoring and troubleshooting
- Customization options
- Architecture diagrams

## Output Structure

Files are organized differently depending on the mode:

### Personal Flights (Default Mode)

Files organized by year:

```
downloads/
├── 2024/
│   ├── flight1.igc
│   ├── flight2.igc
│   └── ...
├── 2023/
│   ├── flight1.igc
│   └── ...
└── 2022/
    └── ...
```

### Public Flights (--all-pilots mode)

Files organized by airport code, then year:

```
downloads/
├── STAUB1/
│   ├── 2024/
│   │   ├── 2024_PilotName_12345.igc
│   │   ├── 2024_AnotherPilot_12346.igc
│   │   └── ...
│   ├── 2023/
│   │   └── ...
│   └── metadata.json
└── STERL1/
    ├── 2024/
    └── ...
```

The `metadata.json` file contains flight information (date, pilot, airport, points, etc.) for each downloaded flight.

## Configuration

### Credentials Storage

Credentials are stored in `~/.olc-downloader/config.env` with restricted permissions (600).

You can also set credentials via environment variables:

```bash
export OLC_USERNAME=your_username
export OLC_PASSWORD=your_password
olc-download download
```

### Custom Download Directory

```bash
# Via command line
olc-download download --output /path/to/backup

# Via environment variable
export OLC_DOWNLOAD_DIR=/path/to/backup
olc-download download
```

## Troubleshooting

### Authentication Failed

- Verify your credentials are correct
- Check if you can log in via the website
- Try reconfiguring: `olc-download configure`

### No Flights Found

- Ensure you're logged in with the correct account
- Check if flights exist on the website
- Try with verbose mode: `olc-download download --verbose`

### Connection Issues / Timeouts

- Check your internet connection
- The OLC website might be temporarily down or slow (504 Gateway Timeout errors are common)
- The flightbook pages can be slow to load - be patient
- Try again later if you get repeated timeouts
- Consider downloading one year at a time: `olc-download download --year 2024`

### Missing Dependencies

If you get import errors, ensure all dependencies are installed:

```bash
pip install -r requirements.txt
# Or reinstall the package:
pip install -e .
```

## Development

### Project Structure

```
src/olc_downloader/
├── __init__.py         # Package initialization
├── cli.py              # CLI interface
├── config.py           # Configuration management
├── auth.py             # Authentication module
├── scraper.py          # IGC discovery/scraping
├── downloader.py       # Download manager
└── exceptions.py       # Custom exceptions
```

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/

# Lint code
ruff check src/
```

## Dependencies

- **requests**: HTTP requests and session management
- **click**: CLI framework
- **rich**: Terminal UI and progress bars
- **beautifulsoup4**: HTML parsing
- **python-dotenv**: Environment variable management
- **lxml**: Fast HTML/XML parsing

## License

This tool is provided as-is for personal use to backup your flight data from OLC.

## Acknowledgments

Thanks to the OLC (Online Contest) platform for providing years of flight tracking services to the soaring community.

## Support

If you encounter issues:

1. Check the troubleshooting section
2. Run with `--verbose` flag for detailed logs
3. Check OLC website accessibility
4. Review the logs in verbose mode for specific errors

## Important Notes

- This tool is designed for **personal use only** to download your own flight data
- **OLC has a 20 flights per day download limit** - plan your backups accordingly
- Respect the OLC website's resources - the tool includes appropriate delays
- Always verify your credentials are stored securely
- Make backups of your downloaded IGC files in multiple locations
- Good news: OLC will continue operating beyond September 2025!
