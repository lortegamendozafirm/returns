# test_sheets_sa.py
import os
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = "1Dyq4QJgwKcW3LEAetga43CkAdvzBZDtW7vLddPugVfo"
SHEET_NAME = "local"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_service():
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not sa_path or not os.path.exists(sa_path):
        raise SystemExit("Falta GOOGLE_APPLICATION_CREDENTIALS o el archivo no existe.")
    creds = service_account.Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def main():
    svc = get_service()
    a1 = "A1"
    value = f"SA_OK {int(time.time())}"

    # Escribe
    body = {"values": [[value]]}
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!{a1}",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()

    # Lee
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!{a1}",
    ).execute()

    print("Escrito:", value)
    print("Leído  :", resp.get("values", [["<sin valor>"]])[0][0])

if __name__ == "__main__":
    main()
