#!/bin/bash
# Quick setup script for Docker usage

set -e

echo "🐳 Control D Sync - Docker Setup"
echo "================================"

# Check if Docker is installed
if ! command -v docker &>/dev/null; then
	echo "❌ Docker is not installed. Please install it first."
	exit 1
fi

# Build the image
echo ""
echo "📦 Building Docker image..."
docker build -t ctrld-sync:latest .

# Display usage instructions
echo ""
echo "✅ Build complete!"
echo ""
echo "📝 Usage examples:"
echo ""
echo "1. Dry run with default folders:"
echo "   docker run --rm -e TOKEN=your-token ctrld-sync:latest --profiles your-profile-id --dry-run"
echo ""
echo "2. Dry run with Docker Compose:"
echo "   docker compose run --rm ctrld-sync --profiles your-profile-id --dry-run"
echo ""
echo "3. Live sync (requires TOKEN and PROFILE in .env):"
echo "   docker compose run --rm ctrld-sync --profiles your-profile-id"
echo ""
echo "4. Clear cache:"
echo "   docker compose run --rm ctrld-sync --clear-cache"
echo ""
