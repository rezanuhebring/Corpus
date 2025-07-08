# /agent/agent.py

import os
import time
import requests
import configparser
import json
from datetime import datetime

# --- Configuration ---
CONFIG_FILE = 'config.ini'
CACHE_FILE = '.agent_cache.json'

def load_config():
    """Loads configuration from config.ini"""
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Configuration file '{CONFIG_FILE}' not found.")
        print("Please copy 'config.ini.example' to 'config.ini' and fill in your details.")
        return None
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config

def load_cache():
    """Loads the cache of already processed files."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_cache(cache):
    """Saves the cache of processed files."""
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=4)

def upload_document(file_path, config):
    """Uploads a single document file to the central server."""
    server_url = config['server']['server_url']
    api_key = config['server']['api_key']
    
    headers = {
        'X-API-Key': api_key
    }
    
    try:
        with open(file_path, 'rb') as f:
            files = {'document': (os.path.basename(file_path), f)}
            print(f"  -> Uploading '{os.path.basename(file_path)}' to server...")
            response = requests.post(server_url, headers=headers, files=files, timeout=60)
            
            if response.status_code == 202:
                print(f"  -> {GREEN}Success:{NC} Server accepted '{os.path.basename(file_path)}' for processing.")
                return True
            else:
                print(f"  -> {RED}Error:{NC} Server returned status {response.status_code}. Response: {response.text}")
                return False
                
    except requests.exceptions.RequestException as e:
        print(f"  -> {RED}Fatal Error:{NC} Could not connect to the server at {server_url}. Please check the URL and your network connection.")
        print(f"     Details: {e}")
        return False

def scan_and_process(config):
    """Scans the directory and uploads new or modified files."""
    scan_dir = config['agent']['scan_directory']
    if not os.path.isdir(scan_dir):
        print(f"{RED}Error:{NC} The scan directory '{scan_dir}' does not exist. Please check your config.ini.")
        return

    print(f"\nScanning directory: {scan_dir}")
    
    cache = load_cache()
    files_processed_this_run = 0

    for root, _, files in os.walk(scan_dir):
        for filename in files:
            # Check for supported file extensions
            if not filename.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.wpd', '.txt')):
                continue

            file_path = os.path.join(root, filename)
            
            try:
                mod_time = os.path.getmtime(file_path)
                file_mod_time_str = str(mod_time)

                # Check cache: if file is new or has been modified since last scan
                if file_path not in cache or cache[file_path] != file_mod_time_str:
                    print(f"Found new/modified file: {filename}")
                    if upload_document(file_path, config):
                        cache[file_path] = file_mod_time_str
                        files_processed_this_run += 1
                
            except FileNotFoundError:
                # File might have been deleted between os.walk and os.path.getmtime
                continue
            except Exception as e:
                print(f"{RED}Error processing file {file_path}:{NC} {e}")

    if files_processed_this_run > 0:
        save_cache(cache)
        print(f"Finished scan. Processed {files_processed_this_run} new/modified documents.")
    else:
        print("No new or modified documents found.")


if __name__ == "__main__":
    # --- For color in terminals ---
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    NC = '\033[0m'

    print(f"{YELLOW}--- Corpus Document Agent ---{NC}")
    
    config = load_config()
    if config:
        scan_interval = int(config['agent'].get('scan_interval_seconds', 60))
        print("Configuration loaded. Starting initial scan...")
        
        while True:
            scan_and_process(config)
            print(f"\nNext scan in {scan_interval} seconds. Press Ctrl+C to stop.")
            time.sleep(scan_interval)