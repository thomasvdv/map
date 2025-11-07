#!/bin/bash
set -e

# Script to commit and push IGC files, metadata, and state to GitHub
# Can be run from GitHub Actions or command line
#
# Usage:
#   ./scripts/commit_and_push_flights.sh <airport_code> <workflow_type> [run_number]
#
# Arguments:
#   airport_code: Airport code (e.g., STERL1)
#   workflow_type: Type of workflow (daily, manual, or local)
#   run_number: Optional workflow run number (for GitHub Actions)

AIRPORT_CODE="${1:-STERL1}"
WORKFLOW_TYPE="${2:-local}"
RUN_NUMBER="${3:-$(date +%s)}"

echo "======================================="
echo "Committing and pushing flight data"
echo "======================================="
echo "Airport: $AIRPORT_CODE"
echo "Workflow: $WORKFLOW_TYPE"
echo "Run: $RUN_NUMBER"
echo ""

# Configure git if not already configured
if [ -z "$(git config user.name)" ]; then
  echo "Configuring git user..."
  if [ "$WORKFLOW_TYPE" = "local" ]; then
    # Use local git config for local runs
    git config user.name "$(git config --global user.name || echo 'Local User')"
    git config user.email "$(git config --global user.email || echo 'user@local')"
  else
    # Use bot for GitHub Actions
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
  fi
fi

# Add IGC files and metadata
echo "Staging files..."
git add downloads/**/*.igc downloads/**/metadata.json downloads/*_state.json 2>/dev/null || true

# Check if there are any changes
if git diff --staged --quiet; then
  echo "No changes to commit"
  exit 0
fi

# Show what will be committed
echo ""
echo "Files to be committed:"
git diff --staged --name-only

# Commit with appropriate message
echo ""
echo "Committing flight data and state..."
git commit -m "Update flights and metadata [skip ci]

Updated by $WORKFLOW_TYPE workflow run #$RUN_NUMBER
Airport: $AIRPORT_CODE

🤖 Generated with Claude Code"

# Push to remote
echo ""
echo "Pushing to remote..."
git push

echo ""
echo "✓ Flight data and state committed and pushed successfully"
