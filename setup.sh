#!/bin/bash
# /setup.sh

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
set -e

# --- Main Setup Logic ---
echo -e "${GREEN}--- Corpus Central Server Automated Setup ---${NC}"

# --- Step 1: Choose Environment ---
echo -e "\n${YELLOW}Step 1: Choose your deployment environment.${NC}"
PS3="Enter your choice (1 or 2): "
select ENV in "development" "production"; do
    case $ENV in
        development)
            echo -e "You have chosen: ${GREEN}Development (HTTP only)${NC}"
            DOMAIN_NAME="localhost"
            break
            ;;
        production)
            echo -e "You have chosen: ${GREEN}Production (HTTPS with Let's Encrypt SSL)${NC}"
            read -p "Enter your domain name (e.g., corpus.yourcompany.com): " DOMAIN_NAME
            if [ -z "$DOMAIN_NAME" ]; then
                echo -e "${RED}Error: Domain name cannot be empty for production.${NC}"; exit 1
            fi
            read -p "Enter your email address (for SSL certificate notifications): " LETSENCRYPT_EMAIL
            if [ -z "$LETSENCRYPT_EMAIL" ]; then
                echo -e "${RED}Error: Email address cannot be empty for production.${NC}"; exit 1
            fi
            break
            ;;
        *)
            echo "Invalid option. Please choose 1 or 2."
            ;;
    esac
done

# --- Step 2: Install System Dependencies ---
echo -e "\n${YELLOW}Step 2: Installing system dependencies...${NC}"
sudo apt-get update -y
sudo apt-get install -y git curl ca-certificates python3-pip python3-venv

if ! command -v docker >/dev/null; then
    echo "Installing Docker..."
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# Install Certbot for production environment
if [ "$ENV" == "production" ]; then
    echo "Installing Certbot for Let's Encrypt..."
    sudo apt-get install -y certbot
fi

# --- Step 3: Configure Docker Permissions ---
if ! groups $USER | grep &>/dev/null '\bdocker\b'; then
    echo -e "\n${YELLOW}Step 3: Adding user to the 'docker' group...${NC}"
    sudo usermod -aG docker $USER
    echo -e "${RED}IMPORTANT:${NC} You must log out and log back in for this change to take effect."
    echo "Please run 'exit', SSH back in, and run this script again."
    exit 0
fi
echo -e "\n${YELLOW}Step 3: Docker permissions are correct.${NC}"

# --- Step 4: Generate Nginx Configuration ---
echo -e "\n${YELLOW}Step 4: Generating Nginx configuration...${NC}"
if [ "$ENV" == "development" ]; then
    cat << EOF > nginx.conf
server {
    listen 80;
    server_name localhost;
    location / {
        proxy_pass http://web:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    echo "Development nginx.conf created."
else # Production
    # This initial config is just for the certbot challenge
    cat << EOF > nginx.conf
server {
    listen 80;
    server_name $DOMAIN_NAME;
    # Allow certbot to access the .well-known directory for challenges
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF
    echo "Initial production nginx.conf created for SSL challenge."
fi

# --- Step 5: Generate Environment Configuration ---
# (This step is mostly unchanged)
echo -e "\n${YELLOW}Step 5: Generating environment configuration...${NC}"
if [ ! -f ".env" ]; then
    # ... (code to generate .env file as before)
    ADMIN_PASSWORD_PLAIN=""
    while [[ -z "$ADMIN_PASSWORD_PLAIN" ]]; do read -p "Please enter a password for the 'admin' user: " -s ADMIN_PASSWORD_PLAIN; echo; done
    echo "FLASK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(16))')" > .env
    echo "ADMIN_USERNAME=admin" >> .env; echo "ADMIN_PASSWORD=$ADMIN_PASSWORD_PLAIN" >> .env
    echo "API_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
    echo "POSTGRES_USER=corpus_user" >> .env; echo "POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(16))')" >> .env
    echo "POSTGRES_DB=corpus_db" >> .env
fi
echo ".env file is ready."

# --- Step 6: Prepare Dummy ML Model ---
# (This step is unchanged)
echo -e "\n${YELLOW}Step 6: Creating dummy ML model...${NC}"
python3 -m venv venv; source venv/bin/activate; pip3 install scikit-learn==1.5.0 > /dev/null
python3 -c "import pickle; from sklearn.feature_extraction.text import TfidfVectorizer; from sklearn.linear_model import LogisticRegression; from sklearn.pipeline import Pipeline; model = Pipeline([('vectorizer', TfidfVectorizer()), ('classifier', LogisticRegression())]); model.fit(['sample text'], ['default']); pickle.dump(model, open('server/model.pkl', 'wb'))"
deactivate; rm -rf venv
echo "Model created."

# --- Step 7: Launch Services & Obtain SSL (if needed) ---
echo -e "\n${YELLOW}Step 7: Launching services...${NC}"
if [ "$ENV" == "production" ]; then
    echo "Starting Nginx temporarily to obtain SSL certificate..."
    # Create dummy certbot directory
    sudo mkdir -p ./certbot/www
    sudo chmod -R 777 ./certbot # Make it writable by certbot container
    # Start only nginx
    docker compose up -d nginx
    echo "Requesting SSL certificate from Let's Encrypt for $DOMAIN_NAME..."
    sudo certbot certonly --webroot -w ./certbot/www -d $DOMAIN_NAME --email $LETSENCRYPT_EMAIL --rsa-key-size 4096 --agree-tos --non-interactive
    echo "SSL Certificate obtained. Stopping temporary Nginx."
    docker compose down

    # Now, create the final production nginx.conf
    echo "Creating final production Nginx configuration..."
    cat << EOF > nginx.conf
server {
    listen 80;
    server_name $DOMAIN_NAME;
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        return 301 https://\$host\$request_uri;
    }
}
server {
    listen 443 ssl http2;
    server_name $DOMAIN_NAME;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN_NAME/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://web:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
fi

echo "Building and launching all application services..."
docker compose up --build -d

# --- Final Instructions ---
echo -e "\n${GREEN}--- DEPLOYMENT COMPLETE ---${NC}\n"
SERVER_URL="http://localhost"
if [ "$ENV" == "production" ]; then
    SERVER_URL="https://$DOMAIN_NAME"
fi

echo "Corpus is running. It may take a minute for all services to initialize."
echo -e "Access the dashboard at: ${YELLOW}$SERVER_URL${NC}"
echo -e "Login with username: ${GREEN}admin${NC} and the password you set."
echo -e "\n--- Agent Configuration ---"
API_KEY_VALUE=$(grep API_KEY .env | cut -d '=' -f2)
echo "Configure your agent's server_url to ${YELLOW}${SERVER_URL}/api/v1/upload${NC}"
echo -e "Use the following API Key: ${GREEN}$API_KEY_VALUE${NC}"
echo ""