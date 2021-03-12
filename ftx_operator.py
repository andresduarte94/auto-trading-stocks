# import time
# import numpy as np
# from datetime import datetime, timedelta
import sheets_service
from google.cloud import secretmanager_v1beta1 as secretmanager
import ftx

project_id = 'trading-bot-299323'
api_key_name = 'ftx-api-key'
api_secret_name = 'ftx-api-secret'
version = 1

sm_client = secretmanager.SecretManagerServiceClient()
secret_path_1 = sm_client.secret_version_path(project_id, api_key_name, version)
secret_path_2 = sm_client.secret_version_path(project_id, api_secret_name, version)
API_KEY = sm_client.access_secret_version(request={"name": secret_path_1}).payload.data.decode('UTF-8')
API_SECRET = sm_client.access_secret_version(request={"name": secret_path_2}).payload.data.decode('UTF-8')

ftx_client = ftx.FtxClient(api_key=API_KEY, api_secret=API_SECRET)
SPREADSHEET_ID = '1RLqJnfIM2Xjxi0oNw6r1diuGHmR_Lv46eYzjxuEDm4c'


def buy_sl_orders_ftx():
    ticker = sheets_service.getSheetValues('risk_management!A2:A', spreadsheet_id=SPREADSHEET_ID)
    values = sheets_service.getSheetValues('risk_management!B2:F', spreadsheet_id=SPREADSHEET_ID)
    rows_to_delete = []
    for indx, row in enumerate(values):
        pair = f"{ticker[indx][0]}-PERP"
        print(pair)
        buy_type = row[0]
        quantity = float(row[1])
        sl_price = float(row[3])
        if buy_type == 'market':
            orderbook = ftx_client.get_orderbook(pair, 1)
            ask_price = float(orderbook['asks'][0][0])
            ftx_client.place_order(pair, 'buy', ask_price, quantity, type='market')
            print('Buy market made for ' + pair)
        elif buy_type == 'limit':
            entry_price = float(row[2])
            ftx_client.place_order(pair, 'buy', entry_price, quantity, type='limit')
            print('Buy limit set for ' + pair)
        # Set SL order for each trade
        sl_order = ftx_client.place_conditional_order(pair, 'sell', quantity, type='stop', trigger_price=sl_price, reduce_only=True)
        print('SL set for ' + pair)
        # Move row from risk to position sheet and delete rows from risk_management
        market_row = indx + 2
        size_col = f"=D{market_row}*C{market_row}"
        profit_col = f"=ABS(F{market_row}-D{market_row})*G{market_row}*0.99/D{market_row}"
        loss_col = f"=ABS(D{market_row}-E{market_row})*G{market_row}*1.01/D{market_row}"
        r_col = f"=H{market_row}/I{market_row}"
        formulas_cells = [size_col, profit_col, loss_col, r_col, sl_order['id'], 'n']
        is_active = 'no' if buy_type == 'limit' else 'yes'
        ab_cells = [ticker[indx][0], is_active]
        market_row_data = [ab_cells + row[1:5] + formulas_cells]
        position_row = sheets_service.get_last_row('positions!A1:B', spreadsheet_id=SPREADSHEET_ID) + 1
        new_position_range = f"positions!A{position_row}:L{position_row}"
        new_position_body = {'range': new_position_range, 'values': market_row_data}
        sheets_service.setSheetValues(new_position_range, new_position_body, spreadsheet_id=SPREADSHEET_ID)
        rows_to_delete.append(indx + 1)
    sheets_service.delete_positions_rows(rows_to_delete, '495711425', 11, spreadsheet_id=SPREADSHEET_ID)


def place_tp_orders_ftx():
    ticker = sheets_service.getSheetValues('positions!A2:A', spreadsheet_id=SPREADSHEET_ID)
    values = sheets_service.getSheetValues('positions!B2:F', spreadsheet_id=SPREADSHEET_ID)
    tp_order_ids = sheets_service.getSheetValues('positions!L2:L', spreadsheet_id=SPREADSHEET_ID)
    for indx, row in enumerate(values):
        pair = f"{ticker[indx][0]}-PERP"
        quantity = float(row[1])
        tp_price = float(row[4])
        is_active = row[0]
        tp_order_id = tp_order_ids[indx][0]
        if is_active == 'yes' and tp_order_id == 'n':
            tp_order = ftx_client.place_order(pair, 'sell', tp_price, quantity, type='limit', reduce_only=True)
            tp_order_row = indx + 2
            tp_order_data = [[tp_order['id']]]
            tp_order_range = f"positions!L{tp_order_row}"
            tp_order_body = {'range': tp_order_range, 'values': tp_order_data}
            sheets_service.setSheetValues(tp_order_range, tp_order_body, spreadsheet_id=SPREADSHEET_ID)
            print('TP set for ' + pair)


def modify_sl_tp_orders_ftx():
    # print(ftx_client.get_open_orders('BTC-PERP'))
    #
    # client.modify_order(9596912, 50000.0, 1).result()
    # client.cancel_order(9596912).result()
    return 'd'