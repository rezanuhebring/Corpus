#!/bin/bash
# /setup.sh (Final, Complete Version)

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
set -e

echo -e "${GREEN}--- Corpus AI Server (Self-Hosted) Automated Setup ---${NC}"

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
            if [ -z "$DOMAIN_NAME" ]; then echo -e "${RED}Error: Domain name required for production.${NC}"; exit 1; fi
            read -p "Enter your email for SSL alerts: " LETSENCRYPT_EMAIL
            if [ -z "$LETSENCRYPT_EMAIL" ]; then echo -e "${RED}Error: Email address required for production.${NC}"; exit 1; fi
            break
            ;;
        *) echo "Invalid option. Please choose 1 or 2." ;;
    esac
done

# --- Step 2: Install System Dependencies ---
echo -e "\n${YELLOW}Step 2: Checking and installing system dependencies...${NC}"
sudo apt-get update -y
sudo apt-get install -y git curl ca-certificates python3-pip python3-venv
if ! command -v docker >/dev/null; then
    echo "Installing Docker Engine..."
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
if [ "$ENV" == "production" ]; then sudo apt-get install -y certbot; fi
echo "System dependencies are ready."

# --- Step 3: Configure Docker Permissions ---
if ! groups $USER | grep &>/dev/null '\bdocker\b'; then
    echo -e "\n${YELLOW}Step 3: Adding user to the 'docker' group...${NC}"
    sudo usermod -aG docker $USER
    echo -e "${RED}IMPORTANT:${NC} You must log out and log back in for this to take effect."
    echo "Please run 'exit', SSH back into the server, and run this script again."
    exit 0
fi
echo -e "\n${YELLOW}Step 3: Docker permissions are correct.${NC}"

# --- Step 4: Generate Nginx Configuration ---
echo -e "\n${YELLOW}Step 4: Generating Nginx configuration...${NC}"
if [ "$ENV" == "development" ]; then
    cat << EOF > nginx.conf
server { listen 80; server_name localhost; client_max_body_size 100M; location / { proxy_pass http://web:5000; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; } }
EOF
else # Production
    cat << EOF > nginx.conf
server { listen 80; server_name $DOMAIN_NAME; location /.well-known/acme-challenge/ { root /var/www/certbot; } location / { return 301 https://\$host\$request_uri; } }
EOF
fi

# --- Step 5: Generate Environment File ---
echo -e "\n${YELLOW}Step 5: Generating environment file (.env)...${NC}"
if [ -f ".env" ]; then
    echo ".env file already exists. Skipping recreation."
else
    read -p "Please enter a password for the 'admin' user: " -s ADMIN_PASSWORD_PLAIN; echo
    echo "FLASK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(16))')" > .env
    echo "ADMIN_USERNAME=admin" >> .env; echo "ADMIN_PASSWORD=$ADMIN_PASSWORD_PLAIN" >> .env
    echo "API_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
    echo "POSTGRES_USER=corpus_user" >> .env; echo "POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(16))')" >> .env
    echo "POSTGRES_DB=corpus_db" >> .env
    echo ".env file created."
fi

# --- Step 6: Prepare Dummy ML Model ---
echo -e "\n${YELLOW}Step 6: Creating dummy ML model...${NC}"
rm -rf venv; python3 -m venv venv; source venv/bin/activate; pip3 install scikit-learn==1.5.0 > /dev/null
python3 -c "import pickle; from sklearn.feature_extraction.text import TfidfVectorizer; from sklearn.linear_model import LogisticRegression; from sklearn.pipeline import Pipeline; model = Pipeline([('vectorizer', TfidfVectorizer()), ('classifier', LogisticRegression())]); model.fit(['contract text', 'invoice text'], ['Contract', 'Finance']); pickle.dump(model, open('server/model.pkl', 'wb'))"
deactivate; rm -rf venv
echo "Model created."

# --- Step 7: Launch Services & Obtain SSL (if needed) ---
echo -e "\n${YELLOW}Step 7: Launching services...${NC}"
if [ "$ENV" == "production" ]; then
    sudo mkdir -p ./certbot/www; sudo chmod -R 777 ./certbot
    docker compose up -d nginx
    echo "Requesting SSL certificate from Let's Encrypt..."
    sudo certbot certonly --webroot -w ./certbot/www -d $DOMAIN_NAME --email $LETSENCRYPT_EMAIL --rsa-key-size 4096 --agree-tos --non-interactive
    docker compose down
    echo "Creating final production Nginx configuration..."
    cat << EOF > nginx.conf
server { listen 80; server_name $DOMAIN_NAME; location /.well-known/acme-challenge/ { root /var/www/certbot; } location / { return 301 https://\$host\$request_uri; } }
server { listen 443 ssl http2; server_name $DOMAIN_NAME; client_max_body_size 100M; ssl_certificate /etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem; ssl_certificate_key /etc/letsencrypt/live/$DOMAIN_NAME/privkey.pem; include /etc/letsencrypt/options-ssl-nginx.conf; ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; location / { proxy_pass http://web:5000; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; } }
EOF
fi

echo "Building and launching all application services..."
docker compose up --build -d

# --- Final Instructions ---
echo -e "\n${GREEN}--- DEPLOYMENT COMPLETE ---${NC}\n"
# ... (rest of the script)