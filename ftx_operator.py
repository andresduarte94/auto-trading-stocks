# import time
# import numpy as np
# from datetime import datetime, timedelta
import json
import requests
import datetime
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
    values = sheets_service.getSheetValues('risk_management!A2:L', spreadsheet_id=SPREADSHEET_ID)
    rows_to_delete = []
    for indx, row in enumerate(values):
        ticker = row[0]
        pair = f"{ticker}/USD"
        print(pair)
        buy_type = row[1]
        print(buy_type)
        quantity = float(row[2])
        entry_price = float(row[3])
        sl_price = float(row[4])
        loss = row[9]
        exchange = row[11]
        limit_order_id = 'n'
        # Set market or limit buy order
        if buy_type == 'market':
            orderbook = ftx_client.get_orderbook(pair, 3)
            ask_price = float(orderbook['asks'][2][0])
            ftx_client.place_order(pair, 'buy', ask_price, quantity, type='market')
            entry_price = ask_price
            print('Buy market made for ' + pair)
        elif buy_type == 'limit':
            buy_order = ftx_client.place_order(pair, 'buy', entry_price, quantity, type='limit')
            entry_price = buy_order['price']
            limit_order_id = buy_order['id']
            print('Buy limit set for ' + pair)
        # Set SL order for each trade
        sl_order = ftx_client.place_conditional_order(pair, 'sell', quantity, type='stop', trigger_price=sl_price)
        print('SL set for ' + pair)
        print(limit_order_id)
        # Move row from risk to position sheet and delete rows from risk_management
        position_row = sheets_service.get_last_row('positions!A1:B', spreadsheet_id=SPREADSHEET_ID) + 1
        is_active = 'no' if buy_type == 'limit' else 'yes'
        size_col = f"=D{position_row}*C{position_row}"
        profit_col = f"=ABS(F{position_row}-D{position_row})*G{position_row}*0.99/D{position_row}"
        loss_col = f"=(E{position_row}-D{position_row})*G{position_row}*1.01/D{position_row}"
        r_col = f"=ABS(H{position_row}/{loss})"
        market_row_data = [
            [ticker, is_active, quantity, entry_price, sl_order['triggerPrice'], row[5], size_col, profit_col,
             loss_col, r_col, sl_order['id'], 'n', limit_order_id, exchange]]
        new_position_range = f"positions!A{position_row}:N{position_row}"
        sheets_service.setSheetValues(new_position_range, market_row_data, spreadsheet_id=SPREADSHEET_ID)
        rows_to_delete.append(indx + 1)
    sheets_service.delete_positions_rows(rows_to_delete, '495711425', 12, spreadsheet_id=SPREADSHEET_ID)


def place_tp_orders_ftx():
    ticker = sheets_service.getSheetValues('positions!A2:A', spreadsheet_id=SPREADSHEET_ID)
    values = sheets_service.getSheetValues('positions!B2:F', spreadsheet_id=SPREADSHEET_ID)
    tp_order_ids = sheets_service.getSheetValues('positions!L2:L', spreadsheet_id=SPREADSHEET_ID)
    for indx, row in enumerate(values):
        pair = f"{ticker[indx][0]}/USD"
        quantity = float(row[1])
        tp_price = float(row[4])
        is_active = row[0]
        tp_order_id = tp_order_ids[indx][0]
        # Place TP order if needed
        if is_active == 'yes' and tp_order_id == 'n':
            tp_order = ftx_client.place_order(pair, 'sell', tp_price, quantity, type='limit', reduce_only=True)
            tp_order_row = indx + 2
            # Set TP order price
            tp_price_data = [[tp_order['price']]]
            tp_price_range = f"positions!F{tp_order_row}"
            sheets_service.setSheetValues(tp_price_range, tp_price_data, spreadsheet_id=SPREADSHEET_ID)
            # Set TP order ID
            tp_order_data = [[tp_order['id']]]
            tp_order_range = f"positions!L{tp_order_row}"
            sheets_service.setSheetValues(tp_order_range, tp_order_data, spreadsheet_id=SPREADSHEET_ID)
            print('TP set for ' + pair)


def modify_sl_tp_orders_ftx():
    ticker = sheets_service.getSheetValues('positions!A2:A', spreadsheet_id=SPREADSHEET_ID)
    order_ids = sheets_service.getSheetValues('positions!K2:M', spreadsheet_id=SPREADSHEET_ID)
    values = sheets_service.getSheetValues('positions!B2:F', spreadsheet_id=SPREADSHEET_ID)
    for indx, row in enumerate(values):
        pair = f"{ticker[indx][0]}/USD"
        is_active = row[0]
        quantity = float(row[1])
        print(pair)
        sl_new_price = float(row[3])
        tp_new_price = tp_price = float(row[4])
        entry_new_price = limit_price = float(row[2])
        sl_order_id = order_ids[indx][0]
        tp_order_id = order_ids[indx][1]
        limit_order_id = order_ids[indx][2]
        # Get orders' price and ID
        sl_order = ftx_client.get_conditional_orders(pair)[0]
        sl_price = sl_order['triggerPrice']
        limit_orders = ftx_client.get_open_orders(pair)
        for order in limit_orders:
            if order['side'] == 'sell':
                tp_price = order['price']
            if order['side'] == 'buy':
                limit_price = order['price']
        # Modify orders' price and quantity if needed
        order_row = indx + 2
        '''
        if sl_order_id != 'n' and sl_new_price != sl_price:
            # Modify SL order
            sl_order = ftx_client.modify_order(existing_order_id=sl_order_id, price=sl_new_price)
            # Set SL order ID
            sl_order_data = [[sl_order['id']]]
            sl_order_range = f"positions!K{order_row}"
            sheets_service.setSheetValues(sl_order_range, sl_order_data, spreadsheet_id=SPREADSHEET_ID)
            # Set SL order price
            sl_order_data = [[sl_order['price']]]
            sl_order_range = f"positions!E{order_row}"
            sheets_service.setSheetValues(sl_order_range, sl_order_data, spreadsheet_id=SPREADSHEET_ID)
            print('SL order modified for pair: ' + pair)
        '''
        if tp_order_id != 'n' and tp_new_price != tp_price:
            # Modify TP order
            tp_order = ftx_client.modify_order(existing_order_id=tp_order_id, price=tp_new_price)
            # Set TP order ID
            tp_order_data = [[tp_order['id']]]
            tp_order_range = f"positions!L{order_row}"
            sheets_service.setSheetValues(tp_order_range, tp_order_data, spreadsheet_id=SPREADSHEET_ID)
            # Set TP order price
            tp_order_data = [[tp_order['price']]]
            tp_order_range = f"positions!F{order_row}"
            sheets_service.setSheetValues(tp_order_range, tp_order_data, spreadsheet_id=SPREADSHEET_ID)
            print('TP order modified for pair: ' + pair)
        if is_active == 'no' and entry_new_price != limit_price:
            # Modify limit order
            limit_order = ftx_client.modify_order(existing_order_id=limit_order_id, price=entry_new_price)
            # Set limit order ID
            limit_order_data = [[limit_order['id']]]
            limit_order_range = f"positions!M{order_row}"
            sheets_service.setSheetValues(limit_order_range, limit_order_data, spreadsheet_id=SPREADSHEET_ID)
            # Set limit order price
            limit_order_data = [[limit_order['price']]]
            limit_order_range = f"positions!D{order_row}"
            sheets_service.setSheetValues(limit_order_range, limit_order_data, spreadsheet_id=SPREADSHEET_ID)
            print('Limit order modified for pair: ' + pair)


def update_closed_trades_ftx():
    ticker = sheets_service.getSheetValues('positions!A2:A', spreadsheet_id=SPREADSHEET_ID)
    order_ids = sheets_service.getSheetValues('positions!K2:L', spreadsheet_id=SPREADSHEET_ID)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=7)).timestamp()
    for indx, row in enumerate(order_ids):
        pair = f"{ticker[indx][0]}/USD"
        sl_order_id = row[0]
        tp_order_id = row[1]
        sl_last_order_id = str(ftx_client.get_conditional_order_history(pair, 'sell', type='stop', order_type='market',
                                                                        start_time=start_date)[0]['id'])
        tp_last_order_id = str(ftx_client.get_order_history(pair, 'sell', order_type='limit',
                                                            start_time=start_date)[0]['id'])
        print(tp_last_order_id)
        if sl_order_id != sl_last_order_id:
            print('SL was triggered move to history for pair ' + pair)
            # ftx_client.cancel_order(tp_order_id).result()
        elif tp_order_id != tp_last_order_id:
            print('TP was triggered move to history for pair ' + pair)
            # ftx_client.cancel_order(sl_order_id).result()


def update_active_trades_ftx():
    return ''


def test_ftx():
    # print(ftx_client.place_order('ETH/USD', 'buy', 1000, 0.01, type='limit'))
    # print(ftx_client.get_conditional_orders('UNI/USD'))
    buy_sl_orders_ftx()
