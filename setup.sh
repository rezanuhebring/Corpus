#!/bin/bash
# /setup.sh

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
set -e

echo -e "${GREEN}--- Corpus AI Server (Self-Hosted) Automated Setup ---${NC}"

# --- Step 1: Install System Dependencies ---
echo -e "\n${YELLOW}Step 1: Checking and installing system dependencies...${NC}"
sudo apt-get update -y
sudo apt-get install -y git curl ca-certificates python3-pip python3-venv

if ! command -v docker >/dev/null; then
    echo "Installing Docker Engine..."
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
echo "System dependencies are ready."

# --- Step 2: Configure Docker Permissions ---
if ! groups $USER | grep &>/dev/null '\bdocker\b'; then
    echo -e "\n${YELLOW}Step 2: Adding user to the 'docker' group...${NC}"
    sudo usermod -aG docker $USER
    echo -e "${RED}IMPORTANT:${NC} You must log out and log back in for this change to take effect."
    echo "Please run 'exit', SSH back into the server, navigate to this directory, and run this script again."
    exit 0
fi
echo -e "\n${YELLOW}Step 2: Docker permissions are correct.${NC}"

# --- Step 3: Generate Environment File ---
echo -e "\n${YELLOW}Step 3: Generating environment file (.env)...${NC}"
if [ -f ".env" ]; then
    echo ".env file already exists. Skipping creation."
else
    read -p "Please enter a password for the 'admin' user: " -s ADMIN_PASSWORD_PLAIN; echo
    echo "FLASK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(16))')" > .env
    echo "ADMIN_USERNAME=admin" >> .env
    echo "ADMIN_PASSWORD=$ADMIN_PASSWORD_PLAIN" >> .env
    echo "API_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
    echo "POSTGRES_USER=corpus_user" >> .env
    echo "POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(16))')" >> .env
    echo "POSTGRES_DB=corpus_db" >> .env
    echo ".env file created."
fi

# --- Step 4: Prepare Dummy ML Model ---
echo -e "\n${YELLOW}Step 4: Creating dummy ML model...${NC}"
rm -rf venv
python3 -m venv venv; source venv/bin/activate; pip3 install scikit-learn==1.5.0 > /dev/null
python3 -c "import pickle; from sklearn.feature_extraction.text import TfidfVectorizer; from sklearn.linear_model import LogisticRegression; from sklearn.pipeline import Pipeline; model = Pipeline([('vectorizer', TfidfVectorizer()), ('classifier', LogisticRegression())]); DUMMY_TEXTS = ['This is a contract.', 'This is an invoice.']; DUMMY_LABELS = ['Contract', 'Finance']; model.fit(DUMMY_TEXTS, DUMMY_LABELS); pickle.dump(model, open('server/model.pkl', 'wb'))"
deactivate; rm -rf venv
echo "Model created."

# --- Step 5: Build and Launch ---
echo -e "\n${YELLOW}Step 5: Building and launching all services...${NC}"
echo "This will now pull the Ollama LLM model. This one-time download can take 5-15 minutes depending on your network speed."
docker compose up --build -d

# --- Final Instructions ---
echo -e "\n${GREEN}--- DEPLOYMENT COMPLETE ---${NC}\n"
echo "Corpus is running. The initial model download is happening in the background."
echo "You can monitor the progress with: ${GREEN}docker logs -f corpus_model_puller${NC}"
echo "Once the model is downloaded, the application will be fully operational."
echo ""
echo -e "Access the dashboard at: ${YELLOW}http://localhost${NC} (or your server's IP)"
echo -e "Login with username: ${GREEN}admin${NC} and the password you set."
echo ""