from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.cloud import secretmanager_v1beta1 as secretmanager

project_id = 'trading-bot-299323'
sheets_secret = 'auto-trading-sheets-id'
version_1 = 1

client = secretmanager.SecretManagerServiceClient()
secret_path_1 = client.secret_version_path(project_id, sheets_secret, version_1)
response = client.access_secret_version(request={"name": secret_path_1})
SPREADSHEET_ID = response.payload.data.decode('UTF-8')

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file('trading-bot-299323-f6a8dbb0b2c3.json', scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)


def getSheetValues(rangeParam, spreadsheet_id: str = SPREADSHEET_ID):
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=rangeParam).execute()
        values = result.get('values', [])
    except Exception as e:
        print('Error while trying to set sheet values')
        print(e)
        values = []
    return values


def setSheetValues(rangeParam, valuesBody, spreadsheet_id: str = SPREADSHEET_ID):
    try:
        sheet = service.spreadsheets()
        sheet.values().update(spreadsheetId=spreadsheet_id,
                              range=rangeParam, body=valuesBody, valueInputOption='USER_ENTERED',
                              responseValueRenderOption='FORMATTED_VALUE').execute()
    except Exception as e:
        print('Error while trying to set sheet values')
        print(e)


def get_last_row(rangeParam, spreadsheet_id: str = SPREADSHEET_ID):
    values = getSheetValues(rangeParam, spreadsheet_id)
    last_row = len(values)
    return last_row


def delete_positions_rows(rows, sheet_id, last_column, spreadsheet_id: str = SPREADSHEET_ID):
    rowsDeleted = 0
    for row in rows:
        rowNumber = row - rowsDeleted
        deleteRowRequest = [
            {
                'deleteRange': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': rowNumber,
                        'endRowIndex': rowNumber + 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': last_column,
                    },
                    'shiftDimension': 'ROWS',
                }
            }
        ]
        try:
            sheet = service.spreadsheets()
            sheet.batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': deleteRowRequest}).execute()
        except Exception as e:
            print('Error while trying to delete sheet rows. Row number: ' + rowNumber)
            print(e)
        rowsDeleted = rowsDeleted + 1
    print('All rows deleted for sheet ID: ' + sheet_id)
