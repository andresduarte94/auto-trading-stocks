import time
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.cloud import secretmanager_v1beta1 as secretmanager

# project_id = 'trading-bot-299323'
# sheets_secret = 'auto-trading-sheets-id'
# version_1 = 1
# client = secretmanager.SecretManagerServiceClient()
# secret_path_1 = client.secret_version_path(project_id, sheets_secret, version_1)
# response = client.access_secret_version(request={"name": secret_path_1})
SPREADSHEET_ID = '1rrDyKwaWU2Mb-MwRlMnZ0f8NdP_UVoXc9eG4x6dB5Yc'  # response.payload.data.decode('UTF-8')

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file('trading-bot-299323-f6a8dbb0b2c3.json', scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)


def getSheetValues(range_param, spreadsheet_id: str = SPREADSHEET_ID):
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_param).execute()
    time.sleep(2)
    values = result.get('values', [])
    return values


def setSheetValues(range_param, values_data, spreadsheet_id: str = SPREADSHEET_ID):
    request_body = {'range': range_param, 'values': values_data}
    sheet = service.spreadsheets()
    sheet.values().update(spreadsheetId=spreadsheet_id,
                          range=range_param, body=request_body, valueInputOption='USER_ENTERED',
                          responseValueRenderOption='FORMATTED_VALUE').execute()
    time.sleep(2)


def get_last_row(range_param, spreadsheet_id: str = SPREADSHEET_ID):
    values = getSheetValues(range_param, spreadsheet_id)
    last_row = len(values)
    return last_row


def delete_positions_rows(rows, sheet_id, last_column, spreadsheet_id: str = SPREADSHEET_ID):
    sortedRows = sorted(rows, reverse=True)
    for row in sortedRows:
        deleteRowRequest = [
            {
                'deleteRange': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': row,
                        'endRowIndex': row + 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': last_column,
                    },
                    'shiftDimension': 'ROWS',
                }
            }
        ]
        sheet = service.spreadsheets()
        sheet.batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': deleteRowRequest}).execute()
        time.sleep(2)
    print('All rows deleted for sheet ID: ' + sheet_id)
