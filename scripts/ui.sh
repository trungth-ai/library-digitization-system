#!/bin/bash
# UI Management Script - Simplified version

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# =============================================================================
# Commands
# =============================================================================

dev() {
    info "Starting UI in DEVELOPMENT mode (hot reload)..."
    
    # Update .env
    sed -i 's/DOCKER_TARGET=.*/DOCKER_TARGET=development/' .env 2>/dev/null || true
    sed -i 's/NODE_ENV=.*/NODE_ENV=development/' .env 2>/dev/null || true
    
    docker-compose up -d ui
    success "UI started - edit code in ui/src/ to see hot reload"
    docker-compose logs -f ui
}

prod() {
    info "Building UI for PRODUCTION..."
    
    # Update .env
    sed -i 's/DOCKER_TARGET=.*/DOCKER_TARGET=runner/' .env 2>/dev/null || true
    sed -i 's/NODE_ENV=.*/NODE_ENV=production/' .env 2>/dev/null || true
    
    docker-compose build ui
    docker-compose up -d ui
    success "UI started in production mode"
}

rebuild() {
    info "Rebuilding UI from scratch..."
    docker-compose stop ui
    docker-compose rm -f ui
    docker rmi library-digitization-ui 2>/dev/null || true
    docker-compose build --no-cache ui
    success "Rebuild complete"
}

logs() {
    docker-compose logs -f ui
}

restart() {
    info "Restarting UI..."
    docker-compose restart ui
    success "Restarted"
}

shell() {
    info "Opening shell..."
    docker-compose exec ui /bin/sh
}

health() {
    info "Health check..."
    curl -f http://localhost:3000/api/health && success "Healthy" || warn "Unhealthy"
}

# Main
case "${1:-help}" in
    dev) dev ;;
    prod) prod ;;
    rebuild) rebuild ;;
    logs) logs ;;
    restart) restart ;;
    shell) shell ;;
    health) health ;;
    *)
        echo "Usage: $0 {dev|prod|rebuild|logs|restart|shell|health}"
        echo ""
        echo "  dev      - Start with hot reload (edit ui/src → auto refresh)"
        echo "  prod     - Build & run production"
        echo "  rebuild  - Rebuild from scratch"
        echo "  logs     - Show logs"
        echo "  restart  - Restart container"
        echo "  shell    - Open shell in container"
        echo "  health   - Check health"
        ;;
esac