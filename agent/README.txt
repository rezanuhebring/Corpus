Corpus Agent for Windows - Installation Instructions
=====================================================

1. Unzip this package to a new folder on your computer (e.g., create a folder named "CorpusAgent" on your Desktop).

2. In that folder, right-click on `config.ini.example` and rename it to `config.ini`.

3. Open the new `config.ini` file with Notepad.

4. Fill in the required details provided by your administrator:
   - server_url: The full address of the server (e.g., http://123.45.67.89/api/v1/upload)
   - api_key: The long, secret key for your agent.
   - scan_directory: The exact path to the folder or external drive you want to scan.
     Example for an external drive D:
     scan_directory = D:\MyDocuments

     Example for a folder on your desktop:
     scan_directory = C:\Users\YourUsername\Desktop\ScannedDocs

5. Save and close the `config.ini` file.

6. To start the agent, simply double-click on `agent.exe`.

A black command window will appear and show the agent's status as it scans for files. You can minimize this window, but it must remain open for the agent to work. To stop the agent, just close the command window.