from googleapiclient.discovery import build  # Added
from google.oauth2 import service_account

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']  # Modified
creds = service_account.Credentials.from_service_account_file('trading-bot-299323-9915eaa38b25.json', scopes=SCOPES)
SAMPLE_SPREADSHEET_ID = '1rrDyKwaWU2Mb-MwRlMnZ0f8NdP_UVoXc9eG4x6dB5Yc'
service = build('sheets', 'v4', credentials=creds)
positions_sheet_id = '427440165'


def getSheetValues(rangeParam):
    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                                range=rangeParam).execute()
    values = result.get('values', [])
    return values


def setSheetValues(rangeParam, valuesBody):
    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().update(spreadsheetId=SAMPLE_SPREADSHEET_ID,
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
        result = sheet.batchUpdate(spreadsheetId=SAMPLE_SPREADSHEET_ID, body={'requests': deleteRowRequest}).execute()
        rowsDeleted = rowsDeleted + 1
    print('All rows deleted')
