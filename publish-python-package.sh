#!/bin/bash
# Universal Python Package Publisher
# Usage: ./publish-python-package.sh [test|prod] [version]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MODE="${1:-test}"
VERSION="${2:-}"

echo -e "${BLUE}════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Python Package Publisher${NC}"
echo -e "${BLUE}════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Verify we're in a Python package directory
if [ ! -f "pyproject.toml" ] && [ ! -f "setup.py" ]; then
    echo -e "${RED}❌ Error: No pyproject.toml or setup.py found${NC}"
    echo "   Run this script from the root of a Python package"
    exit 1
fi

PACKAGE_NAME=$(grep -m 1 "^name = " pyproject.toml 2>/dev/null | cut -d'"' -f2 || echo "unknown")
CURRENT_VERSION=$(grep -m 1 "^version = " pyproject.toml 2>/dev/null | cut -d'"' -f2 || echo "0.0.0")

echo -e "${GREEN}📦 Package:${NC} $PACKAGE_NAME"
echo -e "${GREEN}📌 Current Version:${NC} $CURRENT_VERSION"
echo ""

# Step 2: Clean previous builds
echo -e "${YELLOW}🧹 Cleaning previous builds...${NC}"
rm -rf dist/ build/ *.egg-info/
echo -e "${GREEN}✓ Clean complete${NC}"
echo ""

# Step 3: Run tests (if they exist)
if [ -f "pytest.ini" ] || [ -d "tests" ]; then
    echo -e "${YELLOW}🧪 Running tests...${NC}"
    if command -v pytest &> /dev/null; then
        python3 -m pytest -v || {
            echo -e "${RED}❌ Tests failed${NC}"
            read -p "Continue anyway? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        }
        echo -e "${GREEN}✓ Tests passed${NC}"
    else
        echo -e "${YELLOW}⚠ pytest not installed, skipping tests${NC}"
    fi
    echo ""
fi

# Step 4: Update version (if provided)
if [ -n "$VERSION" ]; then
    echo -e "${YELLOW}📝 Updating version to $VERSION...${NC}"

    # Update pyproject.toml
    if [ -f "pyproject.toml" ]; then
        sed -i '' "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
        echo -e "${GREEN}✓ Updated pyproject.toml${NC}"
    fi

    # Update __init__.py if it has __version__
    INIT_FILE=$(find . -name "__init__.py" -path "*/$(echo $PACKAGE_NAME | tr '-' '_')/__init__.py" | head -1)
    if [ -n "$INIT_FILE" ] && grep -q "__version__" "$INIT_FILE"; then
        sed -i '' "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" "$INIT_FILE"
        echo -e "${GREEN}✓ Updated $INIT_FILE${NC}"
    fi

    echo ""
fi

# Step 5: Build package
echo -e "${YELLOW}🔨 Building package...${NC}"
python3 -m build
echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Step 6: Check package
echo -e "${YELLOW}🔍 Checking package...${NC}"
python3 -m twine check dist/*
echo -e "${GREEN}✓ Package check passed${NC}"
echo ""

# Step 7: Show what will be published
echo -e "${BLUE}📋 Distribution files:${NC}"
ls -lh dist/
echo ""

# Step 8: Publish
if [ "$MODE" = "test" ]; then
    echo -e "${YELLOW}🚀 Publishing to TestPyPI...${NC}"
    echo -e "${YELLOW}   (Test mode - safe to run)${NC}"
    echo ""

    python3 -m twine upload --repository testpypi dist/* || {
        echo ""
        echo -e "${RED}❌ Upload failed${NC}"
        echo -e "${YELLOW}💡 Setup TestPyPI:${NC}"
        echo "   1. Create account: https://test.pypi.org/account/register/"
        echo "   2. Create API token: https://test.pypi.org/manage/account/token/"
        echo "   3. Run: python3 -m keyring set https://test.pypi.org/legacy/ __token__"
        exit 1
    }

    echo ""
    echo -e "${GREEN}✓ Published to TestPyPI${NC}"
    echo -e "${BLUE}📦 Test install:${NC}"
    echo "   pip install --index-url https://test.pypi.org/simple/ $PACKAGE_NAME"

elif [ "$MODE" = "prod" ]; then
    echo -e "${RED}⚠️  PRODUCTION MODE${NC}"
    echo -e "${YELLOW}   This will publish to the REAL PyPI${NC}"
    echo ""
    read -p "Are you sure? (yes/no) " -r
    echo
    if [[ ! $REPLY = "yes" ]]; then
        echo "Cancelled."
        exit 1
    fi

    echo -e "${YELLOW}🚀 Publishing to PyPI...${NC}"
    python3 -m twine upload dist/* || {
        echo ""
        echo -e "${RED}❌ Upload failed${NC}"
        echo -e "${YELLOW}💡 Setup PyPI:${NC}"
        echo "   1. Create account: https://pypi.org/account/register/"
        echo "   2. Create API token: https://pypi.org/manage/account/token/"
        echo "   3. Run: python3 -m keyring set https://upload.pypi.org/legacy/ __token__"
        exit 1
    }

    echo ""
    echo -e "${GREEN}✓ Published to PyPI${NC}"
    echo -e "${BLUE}📦 Install:${NC}"
    echo "   pip install $PACKAGE_NAME"

    # Step 9: Create git tag
    if [ -n "$VERSION" ]; then
        echo ""
        echo -e "${YELLOW}🏷️  Creating git tag v$VERSION...${NC}"
        git add -A
        git commit -m "Release v$VERSION" || echo "No changes to commit"
        git tag -a "v$VERSION" -m "Release version $VERSION"
        echo -e "${GREEN}✓ Tag created${NC}"
        echo ""
        echo -e "${BLUE}💡 Push tag:${NC}"
        echo "   git push && git push --tags"
    fi
else
    echo -e "${RED}❌ Invalid mode: $MODE${NC}"
    echo "Usage: $0 [test|prod] [version]"
    exit 1
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   ✅ Done!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
