#!/bin/bash
#
# Upload content to Cloudflare R2
#
# This is a wrapper script around the Python CLI tool.
# For more options, use: python -m olc_downloader.cli upload-to-r2 --help
#

set -e

# Check if R2 credentials are set
if [ -z "$R2_ACCOUNT_ID" ] || [ -z "$R2_ACCESS_KEY_ID" ] || [ -z "$R2_SECRET_ACCESS_KEY" ]; then
    echo "❌ R2 credentials not set!"
    echo ""
    echo "Please set these environment variables:"
    echo "  export R2_ACCOUNT_ID=your-account-id"
    echo "  export R2_ACCESS_KEY_ID=your-access-key-id"
    echo "  export R2_SECRET_ACCESS_KEY=your-secret-access-key"
    echo ""
    echo "Or create a .env file with these values and run:"
    echo "  source .env"
    echo ""
    exit 1
fi

# Check if Python CLI is available
if ! python -m olc_downloader.cli --help &> /dev/null; then
    echo "❌ olc_downloader CLI not found!"
    echo ""
    echo "Please install the package:"
    echo "  pip install -e ."
    echo ""
    exit 1
fi

# Check if boto3 is installed
if ! python -c "import boto3" &> /dev/null; then
    echo "❌ boto3 not installed!"
    echo ""
    echo "Please install boto3:"
    echo "  pip install boto3"
    echo ""
    exit 1
fi

echo "🚀 Uploading to Cloudflare R2..."
echo ""

# Default: upload everything
UPLOAD_ARGS="--all"

# Allow user to specify what to upload
if [ "$1" = "--vfr-tiles" ]; then
    UPLOAD_ARGS="--vfr-tiles"
elif [ "$1" = "--satellite-tiles" ]; then
    UPLOAD_ARGS="--satellite-tiles"
elif [ "$1" = "--map" ]; then
    if [ -z "$2" ]; then
        echo "❌ Please specify map file path"
        echo "Usage: $0 --map downloads/STERL1_map.html"
        exit 1
    fi
    UPLOAD_ARGS="--map $2"
fi

# Run the Python CLI upload command
python -m olc_downloader.cli upload-to-r2 $UPLOAD_ARGS --verbose
