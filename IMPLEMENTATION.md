# OLC Downloader - Implementation Details

## Overview

This tool downloads IGC flight files from onlinecontest.org by scraping the website after authentication.

## URL Structure

The OLC website uses the following URL patterns for accessing flight data:

### 1. Flightbook (Main Page)
```
https://www.onlinecontest.org/olc-3.0/gliding/flightbook.html?rt=olc&st=olcp&pi=PILOT_ID&sp=YEAR
```
- **pi**: Pilot ID (discovered after login)
- **sp**: Season/Year (e.g., 2024)
- **rt**: Route type (olc)
- **st**: Statistics type (olcp)

### 2. Flight Info
```
https://www.onlinecontest.org/olc-3.0/gliding/flightinfo.html?dsId=DATASET_ID&f_map=
```
- **dsId**: Dataset ID for specific flight

### 3. IGC Download
```
https://www.onlinecontest.org/olc-3.0/gliding/download.html?flightId=FLIGHT_ID
```
- **flightId**: Unique flight identifier (can be negative)

## Authentication Flow

1. **Login URL**: `https://www.onlinecontest.org/olc-3.0/secure/login.html`
2. **Form Fields**:
   - `_ident_`: Username
   - `_name__`: Password
   - `ok_par.x`: Submit button value (1)
3. **Success Indicator**: Look for "logout" or "abmelden" in response

## Scraping Strategy

### Step 1: Get Pilot ID
After successful login, the pilot ID is extracted from the main gliding page:
```python
response = session.get("https://www.onlinecontest.org/olc-3.0/gliding/index.html")
pilot_id = re.search(r'pi=(\d+)', response.text).group(1)
```

### Step 2: Iterate Through Years (2007-2026)
For each year, fetch the flightbook page:
```python
url = f"https://www.onlinecontest.org/olc-3.0/gliding/flightbook.html?rt=olc&st=olcp&pi={pilot_id}&sp={year}"
```

### Step 3: Extract Flight IDs
Three methods are attempted (in order):

1. **Direct Download Links**: Look for `<a href="download.html?flightId=...">` links
2. **Flight Info Links**: Look for `<a href="flightinfo.html?dsId=...">` links
3. **JavaScript/Data**: Search page source for `flightId` patterns

### Step 4: Construct Download URLs
```python
download_url = f"https://www.onlinecontest.org/olc-3.0/gliding/download.html?flightId={flight_id}"
```

## Rate Limiting

**Important**: OLC limits downloads to **20 IGC files per day** per user.

The tool includes:
- Small delays between year requests (0.5s)
- Proper timeout handling (30s default)
- Graceful error handling for timeouts

## Server Issues

The OLC server can be slow or return 504 Gateway Timeout errors. This is normal and expected. The tool handles this by:

1. Using appropriate timeouts
2. Logging warnings instead of failing completely
3. Continuing to next year if one fails

## Testing

Due to server timeouts during development, the tool may need real-world testing with:
1. A working OLC account
2. Actual flight data
3. Patient waiting for slow server responses

### Quick Test
```bash
# Test authentication
olc-download list-years

# Test single year download
olc-download download --year 2024 --dry-run

# Full download (respecting 20 files/day limit)
olc-download download
```

## File Naming

IGC files are named: `{year}_{flight_id}.igc`

Example: `2024_-629493631.igc`

## Limitations

1. **20 files per day limit** - You'll need multiple days to download all flights
2. **Server timeouts** - The OLC server can be slow
3. **No API** - Must scrape HTML (brittle if site changes)
4. **Date extraction** - May be "unknown" if not found in HTML

## Future Improvements

1. Add retry logic with exponential backoff
2. Implement download resume/checkpoint system
3. Better date extraction from flight data
4. Handle flightinfo page resolution for dsId-only links
5. Add progress tracking across multiple sessions (for 20/day limit)
6. Cache pilot ID between sessions
7. Add rate limit tracking (warn when approaching 20 files)

## Dependencies

- **requests**: HTTP session management
- **beautifulsoup4**: HTML parsing
- **lxml**: Fast HTML parser
- **click**: CLI framework
- **rich**: Terminal UI and progress bars
- **python-dotenv**: Credential management
