#!/bin/bash
# =============================================================================
# publish.sh — Safely publish to public repo
# Usage: bash scripts/publish.sh "v1.25.0: description"
# =============================================================================
set -euo pipefail

# --- Configuration -----------------------------------------------------------
PUBLIC_REMOTE="public"
PUBLIC_BRANCH="public-release"
COMMIT_MSG="${1:-Update public release}"

# Files/dirs to EXCLUDE from public repo (add new private items here)
EXCLUDE=(
    "CLAUDE.md"
    "user-claude.md"
    ".claude/"
    "Dockerfile"
    ".dockerignore"
    "docker-compose.yml"
    "archive/"
    "docs/archive/"
    "scripts/archive/"
    "src/archive/"
    "tests/archive/"
    "tests/web/"
    "web/"
    ".streamlit/"
    "data/extracted/"
    "docs/HOW_TO_RUN_kr.md"
    "docs/IMPLEMENTATION_PLAN_v1.20.md"
    "docs/ONTOLOGY_REDESIGN_PLAN.md"
    "docs/screenshots/"
    "docs/user_guide.md"
)

# --- Safety checks -----------------------------------------------------------
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "❌ Error: Must run from 'main' branch (currently on '$CURRENT_BRANCH')"
    exit 1
fi

if ! git remote get-url "$PUBLIC_REMOTE" &>/dev/null; then
    echo "❌ Error: Remote '$PUBLIC_REMOTE' not found"
    echo "   Run: git remote add public https://github.com/grotyx/research-graphDB.git"
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Error: Working tree not clean. Commit or stash changes first."
    exit 1
fi

echo "📦 Publishing to public repo..."
echo "   Message: $COMMIT_MSG"
echo ""

# --- Step 1: Switch to public-release branch ---------------------------------
echo "[1/5] Switching to $PUBLIC_BRANCH..."
git checkout "$PUBLIC_BRANCH"

# --- Step 2: Pull latest from main -------------------------------------------
echo "[2/5] Pulling latest code from main..."
git checkout main -- .

# --- Step 3: Remove excluded files --------------------------------------------
echo "[3/5] Removing private/unnecessary files..."
for item in "${EXCLUDE[@]}"; do
    if git ls-files --error-unmatch "$item" &>/dev/null 2>&1; then
        git rm --cached -r "$item" 2>/dev/null
        rm -rf "$item" 2>/dev/null
        echo "   Removed: $item"
    fi
done

# --- Step 4: Ensure .gitignore excludes private items -------------------------
echo "[4/5] Updating .gitignore..."
for item in "user-claude.md" ".claude/"; do
    if ! grep -q "^${item}$" .gitignore 2>/dev/null; then
        echo "$item" >> .gitignore
        echo "   Added to .gitignore: $item"
    fi
done
git add .gitignore

# --- Step 5: Scan for sensitive data ------------------------------------------
echo "[5/5] Scanning for sensitive data..."
ISSUES=0

# Check for personal paths
if grep -rl "/Users/sangminpark" --include="*.md" --include="*.py" --include="*.yml" --include="*.yaml" . 2>/dev/null | grep -v ".git/"; then
    echo "⚠️  WARNING: Found personal paths in files above"
    ISSUES=$((ISSUES + 1))
fi

# Check for API keys
if grep -rl "sk-ant-api03-[a-zA-Z0-9]" --include="*.py" --include="*.md" --include="*.env" . 2>/dev/null | grep -v ".git/"; then
    echo "⚠️  WARNING: Found potential API keys in files above"
    ISSUES=$((ISSUES + 1))
fi

# Check for hardcoded passwords (not placeholders)
if grep -rn "password.*=.*['\"][a-zA-Z0-9]\{8,\}['\"]" --include="*.py" . 2>/dev/null | grep -v "test_\|placeholder\|example\|your.password\|<" | grep -v ".git/"; then
    echo "⚠️  WARNING: Found potential hardcoded passwords"
    ISSUES=$((ISSUES + 1))
fi

if [ "$ISSUES" -gt 0 ]; then
    echo ""
    echo "❌ Found $ISSUES potential issues. Review above and fix before publishing."
    echo "   To abort: git checkout main && git checkout -- .gitignore"
    exit 1
fi

echo "✅ No sensitive data found"
echo ""

# --- Commit & Push ------------------------------------------------------------
git add -A
if git diff --cached --quiet; then
    echo "ℹ️  No changes to publish."
    git checkout main
    exit 0
fi

echo "Changes to be published:"
git diff --cached --stat
echo ""
read -p "Proceed with publish? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    git commit -m "$COMMIT_MSG"
    git push "$PUBLIC_REMOTE" "$PUBLIC_BRANCH":main
    echo ""
    echo "✅ Published successfully!"
    echo "   https://github.com/grotyx/research-graphDB"
else
    echo "❌ Aborted. Restoring main branch..."
    git checkout main -- .
fi

# --- Return to main ----------------------------------------------------------
git checkout main
git checkout -- .gitignore 2>/dev/null || true
echo "🏠 Back on main branch."
