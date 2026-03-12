#!/usr/bin/env bash
# PlotLot v2 — Phase 2 Setup Script
# Configures API keys, Vercel env vars, and deploys backend
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo ""
echo "============================================="
echo "  PlotLot v2 — Phase 2 Setup"
echo "  Claude Migration + Demo Reliability"
echo "============================================="
echo ""

# ─── Step 1: Collect API Keys ───────────────────────────────────────────────

info "Step 1: Checking API keys..."

source "$ENV_FILE" 2>/dev/null || true

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo ""
    warn "ANTHROPIC_API_KEY not set."
    echo "  Get it from: https://console.anthropic.com/settings/keys"
    echo "  (Your Max plan includes API credits)"
    echo ""
    read -rp "  Paste your Anthropic API key (sk-ant-...): " ANTHROPIC_API_KEY
    if [ -n "$ANTHROPIC_API_KEY" ]; then
        sed -i '' "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY|" "$ENV_FILE"
        ok "ANTHROPIC_API_KEY saved to .env"
    else
        warn "Skipped — Claude will not be available as primary LLM"
    fi
else
    ok "ANTHROPIC_API_KEY already set (${#ANTHROPIC_API_KEY} chars)"
fi

if [ -z "${GROQ_API_KEY:-}" ]; then
    echo ""
    warn "GROQ_API_KEY not set."
    echo "  Get it from: https://console.groq.com/keys"
    echo "  (Free tier: 30 req/min on Llama 3.3 70B)"
    echo ""
    read -rp "  Paste your Groq API key (gsk_...): " GROQ_API_KEY
    if [ -n "$GROQ_API_KEY" ]; then
        sed -i '' "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$GROQ_API_KEY|" "$ENV_FILE"
        ok "GROQ_API_KEY saved to .env"
    else
        warn "Skipped — Groq fallback will not be available"
    fi
else
    ok "GROQ_API_KEY already set (${#GROQ_API_KEY} chars)"
fi

if [ -z "${SENTRY_DSN:-}" ]; then
    echo ""
    warn "SENTRY_DSN not set."
    echo "  Get it from: https://sentry.io → Create project (Next.js) → Copy DSN"
    echo "  (Free tier: 5K errors/month)"
    echo ""
    read -rp "  Paste your Sentry DSN (https://...@...ingest.sentry.io/...): " SENTRY_DSN
    if [ -n "$SENTRY_DSN" ]; then
        sed -i '' "s|^SENTRY_DSN=.*|SENTRY_DSN=$SENTRY_DSN|" "$ENV_FILE"
        ok "SENTRY_DSN saved to .env"
    else
        warn "Skipped — Error tracking will not be active"
    fi
else
    ok "SENTRY_DSN already set"
fi

# Re-source after updates
source "$ENV_FILE" 2>/dev/null || true

# ─── Step 2: Vercel Environment Variables ────────────────────────────────────

echo ""
info "Step 2: Updating Vercel environment variables..."

cd "$FRONTEND_DIR"

if ! command -v vercel &>/dev/null; then
    err "Vercel CLI not installed. Run: npm i -g vercel"
    exit 1
fi

# Check if linked
if [ ! -f "$FRONTEND_DIR/.vercel/project.json" ]; then
    info "Linking Vercel project..."
    vercel link --project mlop_projects --yes
fi

# Set Sentry DSN on Vercel (frontend needs it as NEXT_PUBLIC_)
if [ -n "${SENTRY_DSN:-}" ]; then
    echo "$SENTRY_DSN" | vercel env add NEXT_PUBLIC_SENTRY_DSN production --force 2>/dev/null && \
        ok "NEXT_PUBLIC_SENTRY_DSN set on Vercel (production)" || \
        warn "Could not set NEXT_PUBLIC_SENTRY_DSN (may already exist)"
fi

# Google Maps key
echo ""
read -rp "  Do you have a Google Maps Static API key? (y/n): " HAS_MAPS
if [ "$HAS_MAPS" = "y" ]; then
    read -rp "  Paste your Google Maps key (AIza...): " GOOGLE_MAPS_KEY
    if [ -n "$GOOGLE_MAPS_KEY" ]; then
        echo "$GOOGLE_MAPS_KEY" | vercel env add NEXT_PUBLIC_GOOGLE_MAPS_KEY production --force 2>/dev/null && \
            ok "NEXT_PUBLIC_GOOGLE_MAPS_KEY set on Vercel" || \
            warn "Could not set key (may already exist)"
    fi
else
    echo ""
    warn "Skipped Google Maps. Get a key from:"
    echo "  https://console.cloud.google.com → APIs → Maps Static API → Credentials"
    echo "  Free tier: 28,000 loads/month"
fi

# ─── Step 3: Backend Deployment ──────────────────────────────────────────────

echo ""
info "Step 3: Backend deployment..."
echo ""
echo "  Your Render backend is experiencing cold-start issues."
echo "  Choose a deployment target:"
echo ""
echo "  1) Railway (CLI installed, always-on free tier)"
echo "  2) Keep Render (existing, but has cold-start problem)"
echo "  3) Skip deployment for now"
echo ""
read -rp "  Choice [1/2/3]: " DEPLOY_CHOICE

case "$DEPLOY_CHOICE" in
    1)
        if ! command -v railway &>/dev/null; then
            err "Railway CLI not found. Run: brew install railway"
            exit 1
        fi

        # Check auth
        if ! railway whoami &>/dev/null 2>&1; then
            info "Railway needs authentication..."
            railway login
        fi

        ok "Railway authenticated as: $(railway whoami 2>&1)"

        echo ""
        info "Setting up Railway project..."
        cd "$ROOT_DIR"

        # Init or link project
        if ! railway status &>/dev/null 2>&1; then
            railway init --name plotlot-api
        fi

        # Set environment variables
        info "Setting Railway env vars..."
        railway variables set \
            DATABASE_URL="${DATABASE_URL:-}" \
            ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
            GROQ_API_KEY="${GROQ_API_KEY:-}" \
            NVIDIA_API_KEY="${NVIDIA_API_KEY:-}" \
            GEOCODIO_API_KEY="${GEOCODIO_API_KEY:-}" \
            HF_TOKEN="${HF_TOKEN:-}" \
            JINA_API_KEY="${JINA_API_KEY:-}" \
            SENTRY_DSN="${SENTRY_DSN:-}" \
            OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}" \
            PORT=8000 2>/dev/null

        ok "Environment variables set on Railway"

        # Deploy
        info "Deploying to Railway..."
        railway up --detach

        ok "Deployment started! Check status with: railway status"
        echo ""
        info "After deployment, get your Railway URL with: railway domain"
        info "Then update Vercel NEXT_PUBLIC_API_URL to point to it."
        ;;

    2)
        info "Keeping Render. Current URL: https://plotlot-api.onrender.com"
        warn "Cold starts will persist on Render free tier."

        # Try to update Render env vars if CLI is configured
        if command -v render &>/dev/null; then
            info "Attempting to update Render env vars..."
            warn "Render CLI needs workspace setup. Run: render workspace set"
        fi
        ;;

    3)
        info "Skipping deployment."
        ;;
esac

# ─── Step 4: Update Vercel API URL ──────────────────────────────────────────

echo ""
info "Step 4: Backend URL configuration..."
echo ""
read -rp "  Enter your backend URL (or press Enter to keep current): " BACKEND_URL
if [ -n "$BACKEND_URL" ]; then
    cd "$FRONTEND_DIR"
    echo "$BACKEND_URL" | vercel env add NEXT_PUBLIC_API_URL production --force 2>/dev/null && \
        ok "NEXT_PUBLIC_API_URL updated to: $BACKEND_URL" || \
        warn "Could not update (may need manual update in Vercel dashboard)"

    # Also update local .env.local
    echo "NEXT_PUBLIC_API_URL=$BACKEND_URL" > "$FRONTEND_DIR/.env.local"
    ok "Local .env.local updated"
fi

# ─── Step 5: Verification ───────────────────────────────────────────────────

echo ""
info "Step 5: Running verification..."
echo ""

cd "$ROOT_DIR"

# Backend tests
info "Running backend tests..."
if uv run pytest tests/unit/test_cache_quality.py tests/unit/test_property_type.py tests/unit/test_llm.py -q 2>&1; then
    ok "Phase 2 tests pass (cache quality gate, property type, LLM fallback)"
else
    err "Some tests failed — check output above"
fi

# Frontend build
info "Building frontend..."
cd "$FRONTEND_DIR"
if npx next build 2>&1 | tail -5; then
    ok "Frontend builds successfully"
else
    err "Frontend build failed"
fi

# ─── Summary ────────────────────────────────────────────────────────────────

echo ""
echo "============================================="
echo "  Setup Summary"
echo "============================================="
echo ""
echo "  API Keys:"
[ -n "${ANTHROPIC_API_KEY:-}" ] && ok "  Claude (primary LLM)" || warn "  Claude — NOT SET"
[ -n "${GROQ_API_KEY:-}" ]      && ok "  Groq (secondary LLM)" || warn "  Groq — NOT SET"
[ -n "${NVIDIA_API_KEY:-}" ]    && ok "  NVIDIA (tertiary LLM)" || warn "  NVIDIA — NOT SET"
[ -n "${SENTRY_DSN:-}" ]        && ok "  Sentry (error tracking)" || warn "  Sentry — NOT SET"
echo ""
echo "  Next steps:"
echo "  1. If backend deployed → verify: curl <backend-url>/debug/llm"
echo "  2. If Vercel updated  → redeploy: vercel --prod"
echo "  3. Batch ingest FL municipalities:"
echo "     curl -X POST <backend-url>/api/v1/admin/ingest/batch"
echo "  4. Check admin dashboard: https://mlopprojects.vercel.app/admin"
echo ""
echo "============================================="
