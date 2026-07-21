#!/bin/bash
# Library Digitization System - Installation Script
# Thư viện Đại học Hải Phòng

set -e  # Exit on error

echo "=================================================="
echo "Library Digitization System - Installation"
echo "Hệ thống Số hóa Tài liệu Thư viện HPU"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (sudo)${NC}"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
else
    echo -e "${RED}Cannot detect OS${NC}"
    exit 1
fi

echo -e "${GREEN}Detected OS: $OS $VER${NC}"
echo ""

# Update system
echo "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install Docker
echo ""
echo "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    
    # Add current user to docker group
    if [ -n "$SUDO_USER" ]; then
        usermod -aG docker $SUDO_USER
    fi
    
    echo -e "${GREEN}Docker installed successfully${NC}"
else
    echo -e "${YELLOW}Docker already installed${NC}"
fi

# Install Docker Compose
echo ""
echo "Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}Docker Compose installed successfully${NC}"
else
    echo -e "${YELLOW}Docker Compose already installed${NC}"
fi

# Install NVIDIA Container Toolkit (for GPU support)
echo ""
echo "Installing NVIDIA Container Toolkit..."
if command -v nvidia-smi &> /dev/null; then
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
    curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | tee /etc/apt/sources.list.d/nvidia-docker.list
    
    apt-get update
    apt-get install -y nvidia-docker2
    systemctl restart docker
    
    echo -e "${GREEN}NVIDIA Container Toolkit installed${NC}"
else
    echo -e "${YELLOW}NVIDIA GPU not detected, skipping GPU support${NC}"
fi

# Install Python dependencies (for non-Docker usage)
echo ""
echo "Installing Python dependencies..."
apt-get install -y \
    python3.10 \
    python3-pip \
    python3-dev \
    tesseract-ocr \
    tesseract-ocr-vie \
    tesseract-ocr-eng \
    libtesseract-dev \
    imagemagick \
    ghostscript \
    poppler-utils \
    libopencv-dev \
    python3-opencv

# Install Vietnamese language data for Tesseract
echo ""
echo "Installing Tesseract Vietnamese language data..."
mkdir -p /usr/share/tesseract-ocr/5/tessdata
cd /usr/share/tesseract-ocr/5/tessdata

if [ ! -f "vie.traineddata" ]; then
    wget -q https://github.com/tesseract-ocr/tessdata_best/raw/main/vie.traineddata
    echo -e "${GREEN}Vietnamese language data installed${NC}"
fi

if [ ! -f "eng.traineddata" ]; then
    wget -q https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata
    echo -e "${GREEN}English language data installed${NC}"
fi

# Configure ImageMagick for PDF processing
echo ""
echo "Configuring ImageMagick..."
sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml 2>/dev/null || \
sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-7/policy.xml 2>/dev/null || \
echo -e "${YELLOW}ImageMagick policy file not found, may need manual configuration${NC}"

# Install Python packages
echo ""
echo "Installing Python packages..."
pip3 install --upgrade pip
pip3 install \
    numpy \
    pillow \
    opencv-python \
    pytesseract \
    pypdf \
    pdf2image \
    img2pdf \
    pikepdf \
    anthropic \
    psycopg2-binary \
    redis \
    fastapi \
    uvicorn \
    python-dotenv \
    pydantic

# Create project directories
echo ""
echo "Creating project directories..."
cd /opt
if [ ! -d "library-digitization-system" ]; then
    echo -e "${YELLOW}Please copy project files to /opt/library-digitization-system${NC}"
    mkdir -p library-digitization-system
fi

# Create working directories
mkdir -p /tmp/n8n-digitize
mkdir -p /var/log/library-digitization

# Set permissions
chmod +x /opt/library-digitization-system/scripts/*.py 2>/dev/null || true

# Setup environment file
echo ""
echo "Setting up environment configuration..."
cd /opt/library-digitization-system
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}Created .env file from template${NC}"
        echo -e "${YELLOW}Please edit .env and fill in your configuration${NC}"
    fi
fi

# Database schema: dùng database/init.sql CÓ SẴN trong repo (schema thật: documents,
# job_statuses, metadata_fields, audit_log, extraction_schemas...). KHÔNG tạo/ghi đè ở đây —
# tránh phá schema đúng bằng schema legacy. Postgres tự chạy init.sql khi khởi tạo container lần đầu.
echo ""
if [ -f "database/init.sql" ]; then
    echo -e "${GREEN}Database schema: dùng database/init.sql có sẵn trong repo${NC}"
else
    echo -e "${YELLOW}CẢNH BÁO: thiếu database/init.sql — kéo lại từ repo trước khi deploy${NC}"
fi

# Create systemd service (optional)
echo ""
read -p "Do you want to create a systemd service for auto-start? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cat > /etc/systemd/system/library-digitization.service << EOF
[Unit]
Description=Library Digitization System
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/library-digitization-system
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable library-digitization.service
    echo -e "${GREEN}Systemd service created and enabled${NC}"
fi

# Print completion message
echo ""
echo "=================================================="
echo -e "${GREEN}Installation completed!${NC}"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Edit /opt/library-digitization-system/.env with your configuration"
echo "2. Start services: cd /opt/library-digitization-system && docker-compose up -d"
echo "3. Access n8n: http://localhost:5678"
echo "4. Import workflow from workflows/digitization-workflow.json"
echo "5. Access API documentation: http://localhost:8000/docs"
echo "6. Access monitoring: http://localhost:3000 (Grafana)"
echo ""
echo "For documentation, see: /opt/library-digitization-system/docs/"
echo ""
echo -e "${YELLOW}Important: Configure your .env file before starting!${NC}"
echo "=================================================="

