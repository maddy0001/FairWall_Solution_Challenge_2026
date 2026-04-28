#!/bin/bash
# Run this once in your project root to create the full folder structure
# Usage: bash setup_structure.sh

set -e

echo "Creating FairWall project structure..."

mkdir -p backend/core
mkdir -p backend/api
mkdir -p backend/profiles
mkdir -p backend/models
mkdir -p backend/prompts
mkdir -p backend/setup
mkdir -p frontend/src/components
mkdir -p segments/segment-{1,2,3,4,5,6}
mkdir -p demo
mkdir -p docs
mkdir -p .github/workflows

# Create placeholder files so git tracks empty dirs
touch segments/segment-1/SUMMARY.md
touch segments/segment-1/STEPS.md
touch segments/segment-2/SUMMARY.md
touch segments/segment-2/STEPS.md
touch segments/segment-3/SUMMARY.md
touch segments/segment-3/STEPS.md
touch segments/segment-4/SUMMARY.md
touch segments/segment-4/STEPS.md
touch segments/segment-5/SUMMARY.md
touch segments/segment-5/STEPS.md
touch segments/segment-6/SUMMARY.md
touch segments/segment-6/STEPS.md
touch docs/ARCHITECTURE.md

echo "Done. Structure created:"
find . -type d | grep -v __pycache__ | grep -v .git | sort
