#!/bin/bash
#
# Verify that a map HTML file uses the correct deployment mode
#

if [ $# -eq 0 ]; then
    echo "Usage: $0 <path-to-map.html>"
    echo ""
    echo "This script verifies that a generated map uses the correct tile URLs"
    echo "for the specified deployment mode."
    echo ""
    echo "Examples:"
    echo "  $0 downloads/STERL1/STERL1_map.html"
    echo "  $0 /Users/thomasvdv/GitHub/map/index.html"
    exit 1
fi

MAP_FILE="$1"

if [ ! -f "$MAP_FILE" ]; then
    echo "Error: File not found: $MAP_FILE"
    exit 1
fi

echo "Verifying deployment mode for: $MAP_FILE"
echo ""

# Check for relative URLs (github-pages mode)
if grep -q "url: 'vfr_tiles/tiles/" "$MAP_FILE"; then
    echo "✓ GitHub Pages mode detected"
    echo "  VFR tile URL: vfr_tiles/tiles/{z}/{x}/{y}.png"
    echo ""
    echo "This map is configured for web deployment."
    echo "Deploy to GitHub Pages with: ./deploy_to_github_pages.sh"
    exit 0
fi

# Check for absolute file:// URLs (local mode)
if grep -q "url: 'file:///" "$MAP_FILE"; then
    echo "✓ Local mode detected"
    FILE_URL=$(grep -o "url: 'file://[^']*'" "$MAP_FILE" | head -1)
    echo "  VFR tile URL: ${FILE_URL#url: }"
    echo ""
    echo "This map is configured for local file access."
    echo "Open with: open \"$MAP_FILE\""
    exit 0
fi

# Check for placeholder (not yet processed)
if grep -q "{VFR_TILE_URL}" "$MAP_FILE"; then
    echo "✗ Placeholder detected"
    echo "  The map still contains {VFR_TILE_URL} placeholder"
    echo ""
    echo "This indicates the post-processing step failed."
    echo "The map was generated but not properly configured."
    exit 1
fi

echo "✗ Unknown configuration"
echo "  Could not detect deployment mode from map file"
echo ""
echo "Expected to find one of:"
echo "  - vfr_tiles/tiles/ (github-pages mode)"
echo "  - file:/// (local mode)"
exit 1
