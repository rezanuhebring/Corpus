# Corpus - Centralized Document Intelligence Platform

Corpus is a secure, centralized document classification system. It uses lightweight agents (for Windows, Linux, etc.) to collect documents, which are then processed and categorized by a central server. Administrators can log in to a web dashboard to view, search, and analyze the aggregated document intelligence.

![Architecture Diagram](httpshttps://i.imgur.com/your-diagram-image.png) <!-- It's highly recommended to create and link to a diagram -->

## Features

- **Centralized Processing**: Collects documents from multiple endpoints into a single, managed database.
- **Secure Agent Communication**: Agents use API Key authentication and all traffic is handled over HTTPS.
- **User Authentication**: The main dashboard is protected by a username/password login system.
- **Automated Pipeline**: Documents are automatically processed upon receipt:
    - **Content Extraction**: Uses Apache Tika to parse `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, etc.
    - **ML Classification**: Categorizes documents using a trainable Scikit-learn model.
- **Robust Backend**:
    - **Database**: PostgreSQL for handling concurrent data ingestion and dashboard queries.
    - **Containerized**: All server components are managed by Docker and Docker Compose for reliability and easy deployment.
- **Cross-Platform Agent**: A lightweight Python agent that can be packaged into a standalone `.exe` for Windows users.

## Server Deployment

This server is designed to be deployed on a clean **Ubuntu Server 22.04 LTS** (either in a VM or a cloud instance).

### One-Step Installation

1.  Clone this repository onto your server:
    ```bash
    git clone https://github.com/your-username/corpus.git
    cd corpus
    ```

2.  Make the setup script executable and run it:
    ```bash
    chmod +x setup.sh
    ./setup.sh
    ```

The script will automatically install all dependencies (like Docker), configure the environment, and launch the application. It will prompt you to set an initial admin password and will display the generated API Key for your agents.

### Accessing the Dashboard

Once setup is complete, navigate to your server's IP address or domain name in a web browser.

> **http://<your_server_ip>**

Log in with the username `admin` and the password you set during setup.

## Agent Setup

The agent is located in the `agent/` directory.

1.  Copy the `agent/` folder to the client machine.
2.  Edit the `agent/config.ini` file:
    -   Set `server_url` to the address of your Corpus server (e.g., `http://<your_server_ip>`).
    -   Set `api_key` to the key generated during the server setup.
    -   Set `scan_directory` to the folder you want the agent to watch (e.g., `D:\ExternalDocs`).
3.  Run the agent:
    ```bash
    python agent.py
    ```

For Windows deployment, you can use `pyinstaller` to bundle the agent into a single `.exe`.
```bash
# In the agent directory
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --add-data "config.ini;." agent.py