from google_auth_oauthlib.flow import InstalledAppFlow
# pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

from modules.timetable import get_contacts
from config import cfg

# simple code get auth token to get contact (corporate account required)

if __name__ == '__main__':
    flow = InstalledAppFlow.from_client_secrets_file(cfg.base_dir/'google_credentials.json', ['https://www.googleapis.com/auth/directory.readonly'])
    creds = flow.run_local_server(port=0)
    with open(cfg.base_dir/'temp/auth_token.json', 'w') as token:
        token.write(creds.to_json())
    print('\nToken saved to temp/auth_token.json')
    
    print('\nTest request...')
    print('People count:', len(get_contacts(creds)))
