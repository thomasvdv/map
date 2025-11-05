#!/bin/bash
#
# Deploy map to GitHub Pages
# This script prepares the map for deployment to https://github.com/thomasvdv/map
#

set -e  # Exit on error

# Configuration
MAP_REPO_DIR="/Users/thomasvdv/GitHub/map"
AIRPORT_CODE="STERL1"
SOURCE_DIR="/Users/thomasvdv/GitHub/olc-weglide"
VFR_TILES_SOURCE="${SOURCE_DIR}/vfr_tiles/tiles"

echo "=================================================="
echo "GitHub Pages Deployment Script"
echo "=================================================="
echo ""

# Step 1: Check if map repository exists
if [ ! -d "$MAP_REPO_DIR" ]; then
    echo "[1/5] Creating map repository..."
    mkdir -p "$MAP_REPO_DIR"
    cd "$MAP_REPO_DIR"
    git init
    echo "# Flight Tracking Map" > README.md
    echo ""
    echo "Interactive map of glider flights from Sterling Airport."
    echo ""
    echo "View at: https://thomasvdv.github.io/map" >> README.md
    git add README.md
    git commit -m "Initial commit"
    echo "✓ Repository initialized"
    echo ""
    echo "Next steps to set up the remote:"
    echo "  1. Create repository at: https://github.com/new"
    echo "     Name: map"
    echo "     Don't initialize with README"
    echo "  2. Run these commands:"
    echo "     cd $MAP_REPO_DIR"
    echo "     git remote add origin https://github.com/thomasvdv/map.git"
    echo "     git branch -M main"
    echo "     git push -u origin main"
    echo ""
    read -p "Press Enter when you've created the GitHub repository..."
else
    echo "[1/5] Map repository exists at: $MAP_REPO_DIR"
fi

# Step 2: Generate map with GitHub Pages deployment mode
echo ""
echo "[2/5] Generating map with GitHub Pages deployment mode..."
cd "$SOURCE_DIR"
python -m olc_downloader.cli map \
    --airport-code "$AIRPORT_CODE" \
    --deployment-mode github-pages \
    --output-file "$MAP_REPO_DIR/index.html"

if [ $? -eq 0 ]; then
    echo "✓ Map generated"
else
    echo "✗ Map generation failed"
    exit 1
fi

# Step 3: Copy VFR tiles to map repository
echo ""
echo "[3/6] Copying VFR tiles to map repository..."
echo "This will take a few minutes (copying ~2-5GB of tiles)..."

# Create vfr_tiles directory structure
mkdir -p "$MAP_REPO_DIR/vfr_tiles"

# Use rsync for efficient copying with progress
if command -v rsync &> /dev/null; then
    rsync -ah --info=progress2 "$VFR_TILES_SOURCE/" "$MAP_REPO_DIR/vfr_tiles/tiles/"
else
    cp -R "$VFR_TILES_SOURCE" "$MAP_REPO_DIR/vfr_tiles/tiles"
fi

echo "✓ VFR tiles copied"

# Step 3.5: Copy satellite tiles if they exist
echo ""
echo "[4/6] Copying satellite tiles to map repository (if available)..."
SATELLITE_TILES_SOURCE="${SOURCE_DIR}/vfr_tiles/satellite_tiles"

if [ -d "$SATELLITE_TILES_SOURCE" ]; then
    echo "Found satellite tiles directory, copying..."

    # Count dates (directories in satellite_tiles)
    SATELLITE_DATE_COUNT=$(find "$SATELLITE_TILES_SOURCE" -maxdepth 1 -type d | tail -n +2 | wc -l | tr -d ' ')

    if [ "$SATELLITE_DATE_COUNT" -gt 0 ]; then
        echo "Found $SATELLITE_DATE_COUNT date(s) with satellite tiles..."

        # Use rsync for efficient copying with progress
        if command -v rsync &> /dev/null; then
            rsync -ah --info=progress2 "$SATELLITE_TILES_SOURCE/" "$MAP_REPO_DIR/vfr_tiles/satellite_tiles/"
        else
            mkdir -p "$MAP_REPO_DIR/vfr_tiles/satellite_tiles"
            cp -R "$SATELLITE_TILES_SOURCE"/* "$MAP_REPO_DIR/vfr_tiles/satellite_tiles/"
        fi

        echo "✓ Satellite tiles copied"
    else
        echo "ℹ No satellite tiles found (directory exists but is empty)"
    fi
else
    echo "ℹ No satellite tiles directory found - skipping"
    echo "  To generate satellite tiles, run:"
    echo "    python -m olc_downloader.cli generate-satellite-tiles --airport-code $AIRPORT_CODE --all-dates"
fi

# Step 5: Create .gitignore to exclude large tile files from git
echo ""
echo "[5/6] Creating .gitignore..."
cat > "$MAP_REPO_DIR/.gitignore" << 'EOF'
# Tiles are too large for git - host them via Git LFS or separate CDN
# For now, we'll include them but you may want to use Git LFS
# Uncomment the lines below to exclude tiles from git:
# vfr_tiles/tiles/
# vfr_tiles/satellite_tiles/

# Python
__pycache__/
*.py[cod]
*$py.class
.Python
*.so

# OS
.DS_Store
Thumbs.db
EOF

echo "✓ .gitignore created"

# Step 6: Create deployment documentation
echo ""
echo "[6/6] Creating deployment documentation..."
cat > "$MAP_REPO_DIR/DEPLOYMENT.md" << 'EOF'
# GitHub Pages Deployment

This map is deployed to GitHub Pages at: https://thomasvdv.github.io/map

## Directory Structure

```
map/
├── index.html              # Main map file
├── vfr_tiles/             # Tile assets
│   ├── tiles/              # VFR sectional chart tiles
│   │   └── {z}/{x}/{y}.png
│   └── satellite_tiles/    # Date-specific satellite imagery (optional)
│       └── {YYYY-MM-DD}/
│           └── {z}/{x}/{y}.jpg
├── README.md
└── DEPLOYMENT.md
```

## Initial Setup

1. Create GitHub repository at https://github.com/new
   - Name: `map`
   - Visibility: Public (required for GitHub Pages on free tier)

2. Link local repository to GitHub:
   ```bash
   cd /Users/thomasvdv/GitHub/map
   git remote add origin https://github.com/thomasvdv/map.git
   git branch -M main
   git push -u origin main
   ```

3. Enable GitHub Pages:
   - Go to: https://github.com/thomasvdv/map/settings/pages
   - Source: Deploy from a branch
   - Branch: `main` / `root`
   - Click Save

4. Wait 1-2 minutes for deployment, then visit:
   https://thomasvdv.github.io/map

## Updating the Map

To regenerate and update the map:

```bash
cd /Users/thomasvdv/GitHub/olc-weglide
./deploy_to_github_pages.sh
```

Then commit and push:

```bash
cd /Users/thomasvdv/GitHub/map
git add .
git commit -m "Update map with latest flights"
git push
```

## Storage Considerations

The VFR tiles are approximately 2-5GB. GitHub has the following limits:

- **Repository size**: Recommended < 1GB, hard limit 100GB
- **File size**: Soft limit 50MB, hard limit 100MB
- **Bandwidth**: 100GB/month for free tier

### Options for Large Tiles:

#### Option 1: Include tiles in repository (simplest)
Current setup - tiles are included in git. Works if total size < 1GB.

#### Option 2: Git LFS (Large File Storage)
```bash
cd /Users/thomasvdv/GitHub/map
git lfs install
git lfs track "vfr_tiles/tiles/**/*.png"
git add .gitattributes
```
Note: Git LFS has bandwidth limits (1GB/month free)

#### Option 3: External CDN
Host tiles on a separate service (AWS S3, Cloudflare R2, etc.) and update the tile URL in the map generation.

## Troubleshooting

### Tiles don't load
- Check browser console for errors
- Verify tiles exist at: `vfr_tiles/tiles/10/307/372.png`
- Check GitHub Pages is enabled and deployed

### Map shows blank
- Verify `index.html` was generated with `--deployment-mode github-pages`
- Check that relative paths are used (not `file://` URLs)

### Repository too large
- Use Git LFS (see above)
- Or reduce tile zoom levels (regenerate with `--end_zoom 11` instead of 12)
EOF

echo "✓ Documentation created"

echo ""
echo "=================================================="
echo "✓ Deployment preparation complete!"
echo "=================================================="
echo ""
echo "Map location: $MAP_REPO_DIR/index.html"
echo "VFR tiles: $MAP_REPO_DIR/vfr_tiles/tiles/"

# Show satellite tiles info if they exist
if [ -d "$MAP_REPO_DIR/vfr_tiles/satellite_tiles" ] && [ "$(ls -A "$MAP_REPO_DIR/vfr_tiles/satellite_tiles" 2>/dev/null)" ]; then
    SATELLITE_DATE_COUNT=$(find "$MAP_REPO_DIR/vfr_tiles/satellite_tiles" -maxdepth 1 -type d | tail -n +2 | wc -l | tr -d ' ')
    echo "Satellite tiles: $MAP_REPO_DIR/vfr_tiles/satellite_tiles/ ($SATELLITE_DATE_COUNT dates)"
fi

echo ""
echo "Next steps:"
echo "  1. Review the files in: $MAP_REPO_DIR"
echo "  2. If you haven't already, create the GitHub repository"
echo "  3. Commit and push to GitHub:"
echo "     cd $MAP_REPO_DIR"
echo "     git add ."
echo "     git commit -m 'Initial map deployment'"
echo "     git push"
echo "  4. Enable GitHub Pages in repository settings"
echo "  5. Visit https://thomasvdv.github.io/map"
echo ""
echo "For detailed instructions, see: $MAP_REPO_DIR/DEPLOYMENT.md"
