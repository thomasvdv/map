# High-Resolution VFR Tiles for New England

This setup generates and serves high-quality (300 DPI) VFR sectional chart tiles from official FAA GeoTIFF files.

## Coverage

- **New York Sectional**: Covers southern New England (MA, CT, RI, southern VT/NH, NY)
- **Montreal Sectional**: Covers northern New England (northern VT, NH, ME)

## Current Status

### Completed
✅ Downloaded FAA GeoTIFF files (New York & Montreal sectionals - 145MB)
✅ Extracted source files
✅ Created directory structure
✅ Installed tile generation scripts
⏳ Installing GDAL (in progress - ~10-15 minutes remaining)

### Pending
- Install Python dependencies (5 minutes)
- Run tile generation process (3-5 hours total)
- Set up local tile server
- Update map generator configuration

## Quick Start (After GDAL Installs)

### Option 1: Automated (Recommended)

```bash
cd /Users/thomasvdv/GitHub/olc-weglide
./generate_vfr_tiles.sh
```

This script runs all three stages automatically:
1. Removes map borders/collars (~30-45 min)
2. Reprojects to Web Mercator (~20-30 min)
3. Generates tiles for zoom 8-12 (~2-4 hours)

### Option 2: Manual (For Troubleshooting)

```bash
cd /Users/thomasvdv/GitHub/olc-weglide/tile_generator/scripts

# Install Python dependencies
pip3 install -r ../requirements.txt

# Stage 1: Remove map collars
python3 extract_sectional_charts.py \
    --source_dir ../../vfr_tiles/source \
    --target_dir ../../vfr_tiles/clipped

# Stage 2: Reproject to Web Mercator
python3 reproject_tif.py \
    --input_dir ../../vfr_tiles/clipped \
    --output_dir ../../vfr_tiles/reprojected \
    --target_crs "EPSG:3857"

# Stage 3: Generate tiles (this takes 2-4 hours)
python3 make_slippy_tile.py \
    --start_zoom 8 \
    --end_zoom 12 \
    --input_dir ../../vfr_tiles/reprojected \
    --output_dir ../../vfr_tiles/tiles \
    --tile_size 512
```

## After Tile Generation Completes

### Start the Tile Server

```bash
cd /Users/thomasvdv/GitHub/olc-weglide/vfr_tiles
python3 -m http.server 8000
```

Keep this running in a terminal window. Your tiles will be available at:
`http://localhost:8000/tiles/{z}/{x}/{y}.png`

### Test the Tiles

Open your browser to: `http://localhost:8000/tiles/10/307/372.png`

You should see a high-resolution VFR chart tile.

## Update Your Map Generator

The VFR tile URL in `src/olc_downloader/map_generator.py` has been pre-configured to use:
```javascript
'vfr-local': {
    url: 'http://localhost:8000/tiles/{z}/{x}/{y}.png',
    attr: 'VFR Charts © FAA (Local High-Res)',
    options: {
        minZoom: 8,
        maxZoom: 13,
        maxNativeZoom: 12
    }
}
```

Just generate a new map with `olc-download map --airport-code STERL1` and select "VFR Local" from the layer menu.

## Monitoring Progress

The tile generation process will show progress bars for each zoom level:
- Zoom 8: ~64 tiles (~1 minute)
- Zoom 9: ~256 tiles (~3-5 minutes)
- Zoom 10: ~1,024 tiles (~10-15 minutes)
- Zoom 11: ~4,096 tiles (~45-60 minutes)
- Zoom 12: ~16,384 tiles (~2-3 hours)

## Storage Requirements

- Source GeoTIFFs: ~150MB
- Clipped: ~130MB
- Reprojected: ~200MB
- Tiles (zoom 8-12): ~2-5GB

Total: **~2.5-5.5GB**

## Updating Charts

FAA sectional charts are updated every 56 days. To update:

1. Download new charts from: https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/vfr/
2. Extract to `vfr_tiles/source/`
3. Delete old files in `clipped/`, `reprojected/`, and `tiles/`
4. Re-run `./generate_vfr_tiles.sh`

## Troubleshooting

### "GDAL not found"
Wait for `brew install gdal` to complete (check with `which gdal_translate`)

### "Missing shapefiles"
The tile generator includes shapefiles for all US sectionals in `tile_generator/scripts/shapefiles/`

### Tiles appear blank
- Check that tile server is running on port 8000
- Verify tiles exist in `vfr_tiles/tiles/{z}/{x}/{y}.png`
- Check browser console for CORS or network errors

### Process is taking too long
You can generate only specific zoom levels:
```bash
python3 make_slippy_tile.py --start_zoom 10 --end_zoom 11  # Just zooms 10-11
```

## Comparison: FAA Public Tiles vs. Local High-Res Tiles

| Feature | FAA Public | Local High-Res |
|---------|-----------|----------------|
| Resolution | 96 DPI (256×256px) | 300 DPI (512×512px) |
| Quality | Pixelated | Crystal clear |
| Zoom levels | 8-12 | 8-12 (native) + upscale to 13 |
| Setup time | Instant | 3-5 hours |
| Storage | 0 (cloud) | ~3-5GB local |
| Updates | Automatic | Manual (every 56 days) |
| Requires | Internet | Local server |

The local tiles are approximately **3x higher resolution** and noticeably sharper, especially for reading airport names, frequencies, and airspace boundaries.
