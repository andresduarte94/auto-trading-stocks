from googleapiclient.discovery import build  # Added
from google.oauth2 import service_account
from google.cloud import secretmanager_v1beta1 as secretmanager

project_id = 'trading-bot-299323'
sheets_secret = 'auto-trading-sheets-id'
version_1 = 1

client = secretmanager.SecretManagerServiceClient()
secret_path_1 = client.secret_version_path(project_id, sheets_secret, version_1)
response = client.access_secret_version(request={"name": secret_path_1})
SPREADSHEET_ID = response.payload.data.decode('UTF-8')


SCOPES = ['https://www.googleapis.com/auth/spreadsheets']  # Modified
creds = service_account.Credentials.from_service_account_file('trading-bot-299323-f6a8dbb0b2c3.json', scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
positions_sheet_id = '427440165'


def getSheetValues(rangeParam):
    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                range=rangeParam).execute()
    values = result.get('values', [])
    return values


def setSheetValues(rangeParam, valuesBody):
    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().update(spreadsheetId=SPREADSHEET_ID,
                                   range=rangeParam, body=valuesBody, valueInputOption='USER_ENTERED',
                                   responseValueRenderOption='FORMATTED_VALUE').execute()


def get_last_row(rangeParam):
    values = getSheetValues(rangeParam)
    last_row = len(values)
    return last_row


def delete_positions_rows(rows):
    sheet = service.spreadsheets()
    rowsDeleted = 0
    for row in rows:
        rowNumber = row - rowsDeleted
        deleteRowRequest = [
            {
                'deleteRange': {
                    'range': {
                        'sheetId': positions_sheet_id,
                        'startRowIndex': rowNumber,
                        'endRowIndex': rowNumber + 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': 14,
                    },
                    'shiftDimension': 'ROWS',
                }
            }
        ]
        result = sheet.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'requests': deleteRowRequest}).execute()
        rowsDeleted = rowsDeleted + 1
    print('All rows deleted')
