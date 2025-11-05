# GitHub Pages Deployment Guide

This guide explains how to deploy your flight tracking map to GitHub Pages at `https://thomasvdv.github.io/map`.

## Overview

The deployment process:
1. Generates the map with relative URLs (instead of `file://` URLs)
2. Creates a separate `map` repository
3. Copies the map HTML and VFR tiles to the repository
4. Pushes to GitHub and enables GitHub Pages

## Quick Start

Run the automated deployment script:

```bash
cd /Users/thomasvdv/GitHub/olc-weglide
./deploy_to_github_pages.sh
```

This will:
- Create the `/Users/thomasvdv/GitHub/map` directory
- Generate the map with GitHub Pages deployment mode
- Copy VFR tiles (~2-5GB)
- Create deployment documentation
- Initialize git repository

## Manual Deployment

If you prefer to do it manually:

### 1. Generate Map with GitHub Pages Mode

```bash
cd /Users/thomasvdv/GitHub/olc-weglide
python -m olc_downloader.cli map \
    --airport-code STERL1 \
    --deployment-mode github-pages \
    --output-file /Users/thomasvdv/GitHub/map/index.html
```

The `--deployment-mode github-pages` flag ensures:
- Relative URLs are used: `vfr_tiles/tiles/{z}/{x}/{y}.png`
- Not absolute file:// URLs: `file:///Users/...`

### 2. Copy VFR Tiles

```bash
mkdir -p /Users/thomasvdv/GitHub/map/vfr_tiles
cp -R vfr_tiles/tiles /Users/thomasvdv/GitHub/map/vfr_tiles/
```

### 3. Initialize Git Repository

```bash
cd /Users/thomasvdv/GitHub/map
git init
git add .
git commit -m "Initial commit"
```

### 4. Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `map`
3. Visibility: **Public** (required for free GitHub Pages)
4. Don't initialize with README (you already have files)
5. Click "Create repository"

### 5. Push to GitHub

```bash
cd /Users/thomasvdv/GitHub/map
git remote add origin https://github.com/thomasvdv/map.git
git branch -M main
git push -u origin main
```

### 6. Enable GitHub Pages

1. Go to repository settings: https://github.com/thomasvdv/map/settings/pages
2. Under "Source":
   - Branch: `main`
   - Folder: `/ (root)`
3. Click "Save"

Wait 1-2 minutes for deployment, then visit:
**https://thomasvdv.github.io/map**

## Repository Structure

```
map/
├── index.html              # Interactive map (generated)
├── vfr_tiles/             # VFR sectional chart tiles
│   └── tiles/
│       ├── 8/             # Zoom level 8
│       ├── 9/             # Zoom level 9
│       ├── 10/            # Zoom level 10
│       ├── 11/            # Zoom level 11
│       └── 12/            # Zoom level 12
│           └── {x}/{y}.png
├── README.md
├── DEPLOYMENT.md
└── .gitignore
```

## Updating the Map

After downloading new flights or making changes:

```bash
# Regenerate the map
cd /Users/thomasvdv/GitHub/olc-weglide
python -m olc_downloader.cli map \
    --airport-code STERL1 \
    --deployment-mode github-pages \
    --output-file /Users/thomasvdv/GitHub/map/index.html

# Commit and push
cd /Users/thomasvdv/GitHub/map
git add index.html
git commit -m "Update map with latest flights"
git push
```

GitHub Pages will automatically rebuild and deploy within 1-2 minutes.

## Storage Considerations

### GitHub Limits

- **Repository size**: Recommended < 1GB, hard limit 100GB
- **File size**: Warning at 50MB, error at 100MB
- **Bandwidth**: 100GB/month (free tier)
- **Build time**: 10 minutes max

### VFR Tiles Size

Current tiles (zoom 8-12): **~2-5GB**

This is within GitHub's limits, but be aware of:
- Initial push will take time (large upload)
- Cloning the repo will download all tiles
- Each visitor downloads tiles they view (counts toward bandwidth)

### Options if Size is an Issue

#### Option 1: Reduce Zoom Levels

Generate tiles with fewer zoom levels:

```bash
cd /Users/thomasvdv/GitHub/olc-weglide/tile_generator/scripts
python3 make_slippy_tile.py \
    --start_zoom 9 \
    --end_zoom 11 \
    --input_dir ../../vfr_tiles/reprojected \
    --output_dir ../../vfr_tiles/tiles
```

Zoom 9-11 will reduce tiles to ~500MB-1GB.

#### Option 2: Git LFS (Large File Storage)

Use Git LFS for tiles:

```bash
cd /Users/thomasvdv/GitHub/map
git lfs install
git lfs track "vfr_tiles/tiles/**/*.png"
git add .gitattributes
git add .
git commit -m "Add tiles with LFS"
git push
```

Note: Git LFS free tier is limited to 1GB storage and 1GB bandwidth/month.

#### Option 3: External CDN

Host tiles separately (AWS S3, Cloudflare R2, Netlify, etc.) and update the map generator to point to the CDN URL.

## Troubleshooting

### Map loads but tiles don't show

**Check browser console** (F12):
- Look for 404 errors on tile requests
- Verify URL structure: `vfr_tiles/tiles/10/307/372.png`

**Solutions:**
- Ensure tiles were copied to the repository
- Check GitHub Pages is enabled and deployed
- Verify deployment mode was set to `github-pages`

### GitHub Pages not deploying

- Check Actions tab for build errors
- Verify branch and folder settings in Pages settings
- Ensure repository is public

### Repository size warning

If you see "This repository is over its data quota":
- Use Git LFS (see above)
- Or reduce tile zoom levels
- Or use external CDN

### Tiles load slowly

- VFR tiles are high-resolution (300 DPI, 512x512px)
- Initial load caches tiles in browser
- Consider using CDN for faster global delivery

## Local Testing

Test the map locally before deploying:

```bash
cd /Users/thomasvdv/GitHub/map
python3 -m http.server 8000
```

Open: http://localhost:8000

This simulates how GitHub Pages will serve the files.

## Comparison: Deployment Modes

| Feature | Local Mode | GitHub Pages Mode |
|---------|-----------|------------------|
| VFR Tiles URL | `file:///Users/.../tiles/{z}/{x}/{y}.png` | `vfr_tiles/tiles/{z}/{x}/{y}.png` |
| Use Case | Local development | Web deployment |
| Requires Server | No (direct file access) | Yes (HTTP server) |
| Shareable | No | Yes (public URL) |

## Next Steps

After deployment:

1. **Test the map**: https://thomasvdv.github.io/map
2. **Share the URL** with others
3. **Set up automatic updates**:
   - Create a GitHub Action to regenerate the map weekly
   - Or manually update after downloading new flights
4. **Monitor GitHub Pages**:
   - Check bandwidth usage in repository insights
   - Review any build/deployment errors

## Support

For issues with:
- **Map generation**: Check `/Users/thomasvdv/GitHub/olc-weglide/src/olc_downloader/map_generator.py`
- **Tile generation**: See `/Users/thomasvdv/GitHub/olc-weglide/VFR_TILES_README.md`
- **Deployment**: Review `/Users/thomasvdv/GitHub/map/DEPLOYMENT.md`

## CLI Reference

Generate map for GitHub Pages:
```bash
python -m olc_downloader.cli map --help
```

Options:
- `-a, --airport-code`: Airport code (required)
- `-d, --deployment-mode`: `local` or `github-pages` (default: `local`)
- `-o, --output`: Output directory
- `-f, --output-file`: Output HTML file path
- `-m, --max-tracks`: Limit number of tracks
- `-v, --verbose`: Verbose output
