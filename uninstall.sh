#!/bin/bash
# /uninstall.sh
# A script to completely remove the Corpus AI server and its data.

# --- Style and Color Definitions ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Ensure the script is run from the project root
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}Error: This script must be run from the project's root directory (the one containing docker-compose.yml).${NC}"
    exit 1
fi

set -e

# --- Main Uninstall Logic ---
echo -e "${RED}--- Corpus AI Server Uninstallation ---${NC}"
echo -e "${YELLOW}WARNING: This script will permanently delete all Docker containers, volumes (including databases and uploaded documents), and generated configuration files for this project.${NC}"
read -p "Are you sure you want to continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
fi

# --- Step 1: Stop and Remove All Docker Components ---
echo -e "\n${YELLOW}Step 1: Stopping all services and removing containers, networks, and volumes...${NC}"
if docker compose ps &> /dev/null; then
    docker compose down -v
    echo -e "${GREEN}All services stopped and data volumes (corpus_data, chroma_data, ollama_data, corpus_uploads) have been deleted.${NC}"
else
    echo -e "${GREEN}Docker services not running. Skipping.${NC}"
fi

# --- Step 2: Clean Up Docker Images ---
echo -e "\n${YELLOW}Step 2: Cleaning up Docker images...${NC}"
read -p "Do you want to remove the Docker images built for this project (corpus-web, corpus-ollama, etc.)? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # This command is safe; it only removes images that are not used by any other containers.
    # We specifically target the images built by this project's compose file.
    docker compose build --no-cache # A trick to get the image names without building
    docker compose down --rmi local
    echo -e "${GREEN}Project-specific Docker images have been removed.${NC}"
else
    echo "Skipping image removal."
fi

# --- Step 3: Remove Generated Configuration Files ---
echo -e "\n${YELLOW}Step 3: Removing generated configuration files...${NC}"
rm -f .env
rm -f nginx.conf
echo -e "${GREEN}'.env' and 'nginx.conf' have been deleted.${NC}"

# --- Step 4: Remove SSL Certificates (for Production Installs) ---
echo -e "\n${YELLOW}Step 4: Checking for production SSL certificates...${NC}"
if command -v certbot &> /dev/null; then
    read -p "Did you run the setup in 'production' mode with an SSL certificate? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Please enter the domain name you used (e.g., corpus.yourcompany.com): " DOMAIN_NAME
        if [ -n "$DOMAIN_NAME" ]; then
            echo -e "${RED}This will delete the SSL certificate for ${DOMAIN_NAME} from Certbot.${NC}"
            read -p "Proceed with certificate deletion? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo certbot delete --cert-name "$DOMAIN_NAME"
                echo -e "${GREEN}Certificate for ${DOMAIN_NAME} has been deleted.${NC}"
            else
                echo "Skipping certificate deletion."
            fi
        fi
    fi
else
    echo "Certbot not found. Skipping SSL certificate removal."
fi

# --- Step 5: "Scorched Earth" - Uninstall System Dependencies ---
echo -e "\n${RED}--- Optional: System-Level Uninstallation ---${NC}"
echo -e "${YELLOW}This final step will completely uninstall Docker and Certbot from the system."
echo -e "${RED}WARNING: Only do this if you are sure no other applications on this server use Docker.${NC}"
read -p "Do you want to proceed with uninstalling system dependencies (Docker, etc.)? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstalling Docker, Docker Compose, and Certbot..."
    sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin certbot
    sudo apt-get autoremove -y --purge
    echo "Removing Docker's APT repository..."
    sudo rm -f /etc/apt/sources.list.d/docker.list
    sudo rm -f /etc/apt/keyrings/docker.asc
    sudo apt-get update
    echo -e "${GREEN}System dependencies have been uninstalled.${NC}"
else
    echo "Skipping system dependency uninstallation."
fi

echo -e "\n${GREEN}--- Corpus Uninstallation Complete ---${NC}"
echo "The project directory can now be safely deleted."