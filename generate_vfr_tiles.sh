#!/bin/bash
#
# VFR Tile Generation Script for New England
# This script processes FAA sectional charts (New York & Montreal)
# and generates high-resolution map tiles for use with Leaflet
#

set -e  # Exit on error

# Directories
SOURCE_DIR="/Users/thomasvdv/GitHub/olc-weglide/vfr_tiles/source"
CLIPPED_DIR="/Users/thomasvdv/GitHub/olc-weglide/vfr_tiles/clipped"
REPROJECTED_DIR="/Users/thomasvdv/GitHub/olc-weglide/vfr_tiles/reprojected"
TILES_DIR="/Users/thomasvdv/GitHub/olc-weglide/vfr_tiles/tiles"
SCRIPTS_DIR="/Users/thomasvdv/GitHub/olc-weglide/tile_generator/scripts"

echo "=================================================="
echo "VFR Tile Generation for New England"
echo "=================================================="
echo ""
echo "This process has 3 stages:"
echo "  1. Extract map collars (remove borders) ~30-45 min"
echo "  2. Reproject to Web Mercator          ~20-30 min"
echo "  3. Generate tiles (zoom 8-12)         ~2-4 hours"
echo ""
echo "Total time: 3-5 hours"
echo "=================================================="
echo ""

# Check if GDAL is installed
if ! command -v gdal_translate &> /dev/null; then
    echo "ERROR: GDAL is not installed. Please run: brew install gdal"
    exit 1
fi

# Check if Python packages are installed
if ! python3 -c "import rasterio" 2>/dev/null; then
    echo "Installing Python dependencies..."
    pip3 install -r /Users/thomasvdv/GitHub/olc-weglide/tile_generator/requirements.txt
fi

# Stage 1: Extract map collars
echo "[1/3] Extracting map collars..."
cd "$SCRIPTS_DIR"
python3 extract_sectional_charts.py \
    --source_dir "$SOURCE_DIR" \
    --target_dir "$CLIPPED_DIR"

if [ $? -eq 0 ]; then
    echo "✓ Map collar extraction complete"
else
    echo "✗ Map collar extraction failed"
    exit 1
fi

# Stage 2: Reproject to Web Mercator
echo ""
echo "[2/3] Reprojecting to Web Mercator (EPSG:3857)..."
python3 reproject_tif.py \
    --input_dir "$CLIPPED_DIR" \
    --output_dir "$REPROJECTED_DIR" \
    --target_crs "EPSG:3857"

if [ $? -eq 0 ]; then
    echo "✓ Reprojection complete"
else
    echo "✗ Reprojection failed"
    exit 1
fi

# Stage 3: Generate tiles
echo ""
echo "[3/3] Generating map tiles (this will take 2-4 hours)..."
echo "Progress will be shown as tiles are generated..."
python3 make_slippy_tile.py \
    --start_zoom 8 \
    --end_zoom 12 \
    --input_dir "$REPROJECTED_DIR" \
    --output_dir "$TILES_DIR"

if [ $? -eq 0 ]; then
    echo ""
    echo "=================================================="
    echo "✓ Tile generation complete!"
    echo "=================================================="
    echo ""
    echo "Tiles saved to: $TILES_DIR"
    echo ""
    echo "Next steps:"
    echo "  1. Start tile server: cd vfr_tiles && python3 -m http.server 8000"
    echo "  2. Update map generator to use: http://localhost:8000/tiles"
else
    echo "✗ Tile generation failed"
    exit 1
fi
