import time
import degiroapi
import numpy as np
from degiroapi.order import Order
from datetime import datetime, timedelta
from degiroapi.product import Product
from google.cloud import secretmanager_v1beta1 as secretmanager
import sheets_service
import pandas as pd
import yfinance as yf
from yahoofinancials import YahooFinancials

project_id = 'trading-bot-299323'
username_secret = 'degiro-username'
password_secret = 'degiro-password'

client = secretmanager.SecretManagerServiceClient()
secret_path_1 = client.secret_version_path(project_id, username_secret, 1)
secret_path_2 = client.secret_version_path(project_id, password_secret, 3)
USERNAME = client.access_secret_version(request={"name": secret_path_1}).payload.data.decode('UTF-8')
PASSWORD = client.access_secret_version(request={"name": secret_path_2}).payload.data.decode('UTF-8')

degiro = degiroapi.DeGiro()


def attempt_trade_degiro():
    print('Starting new trade attempt')
    login_de_giro()
    insert_new_positions()
    update_sheets_data()
    update_current_PL_degiro()
    update_trailing_price()
    values = sheets_service.getSheetValues('positions!A2:O')
    for indx, row in enumerate(values):
        trailing_price = float(row[14])
        take_profit = float(row[3])
        quantity = int(row[4])
        product_id = int(row[1])
        close_order = row[10]
        order_changed = row[11]
        order_id = row[12]
        try:
            stock_data = degiro.real_time_price(product_id, degiroapi.Interval.Type.One_Day)[0]['data']
        except Exception as e:
            print('Error while trying to get last stock price for product ID: ' + str(product_id))
            print(e)
            continue
        current_price = stock_data['lastPrice']
        sl_trigger = (current_price - trailing_price) * 100 / current_price
        tp_trigger = (take_profit - current_price) * 100 / current_price
        print(row[0])
        print(current_price)
        print(trailing_price)
        print(take_profit)
        print(" ")
        print(sl_trigger)
        print(tp_trigger)
        if 10 > sl_trigger > 0:
            print('sl trigger')
            create_sell_order(product_id, 'SL', quantity, trailing_price, close_order, order_changed, order_id)
        elif 10 > tp_trigger > 0:
            print('tp trigger')
            create_sell_order(product_id, 'TP', quantity, take_profit, close_order, order_changed, order_id)
        elif tp_trigger < 0 or sl_trigger < 0:
            print('Sold at market order, due to SL or TP breached')
            degiro.sellorder(Order.Type.MARKET, product_id, 3, quantity)
            market_order = 'TP' if tp_trigger < 0 else 'SL'
            market_order_data = [[market_order]]
            row_number = indx + 2
            market_order_range = f"positions!K{row_number}"
            sheets_service.setSheetValues(market_order_range, market_order_data)
        print(" --------------------- ")
    degiro.logout()
    return 'Process finished at ' + datetime.today().strftime('%Y-%m-%d-%H:%M:%S')


def create_sell_order(product_id, order_type, quantiy, price, close_order, order_changed, order_id):
    # Manage existing orders
    if order_id != 'n':
        if order_changed == 'y' or order_type != close_order:
            print(order_changed + ' ' + order_id + ' ' + close_order)
            try:
                degiro.delete_order(order_id)
                time.sleep(2)
            except Exception as e:
                print('Error while trying to delete order ID: ' + order_id)
                print(e)
        else:
            print('No order change needed')
            return
    # Create sell order
    try:
        if order_type == 'SL':
            degiro.sellorder(Order.Type.STOPLOSS, product_id, 3, quantiy, None, price)
            time.sleep(2)
        elif order_type == 'TP':
            degiro.sellorder(Order.Type.LIMIT, product_id, 3, quantiy, price)
            time.sleep(2)
    except Exception as e:
        print('Error while trying to place sell order for product ID: ' + str(product_id))
        print(e)
    print(order_type + ' order placed')


def update_sheets_data():
    values = sheets_service.getSheetValues('positions!A2:P')
    try:
        # Get portafolio data
        portfolio = degiro.getdata(degiroapi.Data.Type.PORTFOLIO, True)
        # Get orders data
        orders = degiro.orders(datetime.now() - timedelta(days=30), datetime.now())
    except Exception as e:
        print('Error while trying to get portafolio or orders data')
        print(e)
        return
    # Create array for positions table data (Add/Delete)
    data_size = sheets_service.get_last_row('positions!A1:A') - 1
    quantity_data = np.full((data_size, 6), 'n').tolist()
    order_data = np.full((data_size, 4), 'n').tolist()
    rows_to_delete = []
    for indx, row in enumerate(values):
        sheets_product_id = row[1]
        trailing_sl_sheet = float(row[14])
        tp_sheet = float(row[3])
        last_position = len(portfolio) - 1
        for port_indx, position in enumerate(portfolio):
            row_number = indx + 2
            if position['id'] == sheets_product_id:
                # Fill quantity and entry_price sheets data
                quantity_data[indx][0] = position['size']
                quantity_data[indx][1] = f'=E{row_number}*G{row_number}*GOOGLEFINANCE("CURRENCY:USDEUR")'
                quantity_data[indx][2] = position['breakEvenPrice']
                quantity_data[indx][3] = f"=(D{row_number}-G{row_number})*F{row_number}/G{row_number}"
                quantity_data[indx][4] = f"=(C{row_number}-G{row_number})*F{row_number}/G{row_number}"
                quantity_data[indx][5] = f"=ABS(H{row_number}/I{row_number})"
                break
            if port_indx == last_position:
                # Get P/L depending on last sell order placed
                close_order = row[10]
                profit = row[7]
                loss = row[15]
                p_l = profit if close_order == 'TP' else loss
                # Set closed position values to positions_history table
                position_history_row = sheets_service.get_last_row('positions_history!A1:A') + 1
                history_range = f"positions_history!A{position_history_row}:L{position_history_row}"
                history_row = row[:10]
                history_row.append(p_l)
                history_row.append(datetime.today().strftime('%Y-%m-%d'))
                history_data = [history_row]
                sheets_service.setSheetValues(history_range, history_data)
                # Add row index to delete rows array
                rows_to_delete.append(indx + 1)
        for order in orders:
            if str(order['productId']) == sheets_product_id:
                if order['isActive'] and order['buysell'] == 'S':
                    # Check if indx is in rows_to_delete, if it is then cancel order with order_id
                    if indx in rows_to_delete:
                        try:
                            degiro.delete_order(order['orderId'])
                            time.sleep(2)
                        except Exception as e:
                            print('Error while trying to get delete sell order ID: ' + order['orderId'])
                            print(e)
                    else:
                        # Fill orderId, tp, sl, price sheets data
                        order_data[indx][2] = order['orderId']
                        if order['orderTypeId'] == Order.Type.LIMIT:
                            order_data[indx][0] = 'TP'
                            order_data[indx][3] = order['price']
                            if tp_sheet != order['price']:
                                order_data[indx][1] = 'y'
                        if order['orderTypeId'] == Order.Type.STOPLOSS:
                            order_data[indx][0] = 'SL'
                            order_data[indx][3] = order['stopPrice']
                            if trailing_sl_sheet != order['stopPrice']:
                                order_data[indx][1] = 'y'
                    break
    # Set quantity, size and entry_price values
    quantity_range = 'positions!E2:J'
    sheets_service.setSheetValues(quantity_range, quantity_data)
    # Set orders information into sheet
    order_range = 'positions!K2:N'
    sheets_service.setSheetValues(order_range, order_data)
    # Delete rows with old positions, this must be the last sheet operation
    sheets_service.delete_positions_rows(rows_to_delete, '427440165', 18)
    print('Sheets are updated')


def insert_new_positions():
    pending_orders = sheets_service.getSheetValues('pending_orders!B2:B')
    product_ids = sheets_service.getSheetValues('positions!B2:B')
    position_row = sheets_service.get_last_row('positions!A1:A') + 1
    current_position_row = position_row
    insert_trades_data = []
    trailing_trades_data = []
    rows_to_delete = []
    try:
        portfolio = degiro.getdata(degiroapi.Data.Type.PORTFOLIO, True)
    except Exception as e:
        print('Error while trying to get portafolio data')
        print(e)
        return
    for portIndx, position in enumerate(portfolio):
        for indx, row in enumerate(pending_orders):
            sheets_product_id = row[0]
            if [sheets_product_id] not in product_ids or len(product_ids) == 0:
                if position['id'] == sheets_product_id:
                    # Get triggered order values from pending_order table
                    pending_order_row = indx + 2
                    pending_order_values = sheets_service.getSheetValues(
                        f"pending_orders!A{pending_order_row}:H{pending_order_row}")
                    # Construct data array ticker, product_id, SL and TP
                    insert_trades_data.append(
                        [pending_order_values[0][0], pending_order_values[0][1], pending_order_values[0][6],
                         pending_order_values[0][7]])
                    # Fill trailing and current P/L data
                    trailing_trades_data.append(
                        [pending_order_values[0][6],
                         f"=(O{current_position_row}-G{current_position_row})*F{current_position_row}/G{current_position_row}"])
                    # Add row index to delete rows
                    rows_to_delete.append(indx + 1)
                    # Update position_row counter
                    current_position_row += 1
    # Set values on position table
    insert_trades_range = f"positions!A{position_row}:D"
    sheets_service.setSheetValues(insert_trades_range, insert_trades_data)
    # Set trailing and current P/L information
    trailing_trades_range = f"positions!O{position_row}:P"
    sheets_service.setSheetValues(trailing_trades_range, trailing_trades_data)
    # Delete rows with old pending orders
    sheets_service.delete_positions_rows(rows_to_delete, '788011985', 11)
    print('New positions have been inserted')


def get_stocks_info():
    login_de_giro()
    stocks = sheets_service.getSheetValues('risk_management!A2:A')
    product_id_data = []
    for item in stocks:
        stock = item[0]
        try:
            products = degiro.search_products(stock)
            product = Product(products[0])
            if product.symbol == stock and product.currency == 'USD':
                product_id_data.append([product.id])
            else:
                product_id_data.append(['Not found'])
        except Exception as e:
            print('Error while trying to get info for stock: ' + stock)
            print(e)
            product_id_data.append(['Exception'])
    product_id_range = "risk_management!B2:B"
    sheets_service.setSheetValues(product_id_range, product_id_data)
    degiro.logout()


def place_buy_orders():
    login_de_giro()
    buy_data = sheets_service.getSheetValues('risk_management!A2:K')
    new_oder_data = []
    rows_to_delete = []
    for indx, row in enumerate(buy_data):
        product_id = row[1]
        quantity = row[2]
        price_limit = row[5]
        try:
            degiro.buyorder(Order.Type.LIMIT, product_id, 3, quantity, price_limit)
            time.sleep(2)
            # Add row index to delete rows array, but avoid first one
            if indx > 0:
                rows_to_delete.append(indx + 1)
        except Exception as e:
            print('Error while trying to place buy order for product ID: ' + product_id)
            print(e)
        new_oder_data.append(row)
    new_oder_range = "pending_orders!A2:K"
    sheets_service.setSheetValues(new_oder_range, new_oder_data)
    # Delete rows in risk_management but the fist one for template usage
    sheets_service.delete_positions_rows(rows_to_delete, '495711425', 11)
    degiro.logout()


def update_current_PL_degiro():
    login_de_giro()
    product_ids = sheets_service.getSheetValues('positions!B2:B')
    current_PL_data = []
    for indx, row in enumerate(product_ids):
        row_number = indx + 2
        product_id = row[0]
        current_price = degiro.real_time_price(product_id, degiroapi.Interval.Type.One_Day)[0]['data']['lastPrice']
        current_PL_data.append([f"=({current_price}-G{row_number})*F{row_number}/G{row_number}"])
    current_PL_range = "positions!Q2:Q"
    sheets_service.setSheetValues(current_PL_range, current_PL_data)


def update_trailing_order_data():
    login_de_giro()
    product_ids = sheets_service.getSheetValues('positions!B2:B')
    quantities = sheets_service.getSheetValues('positions!E2:E')
    orders_data = sheets_service.getSheetValues('positions!L2:O')
    for indx, row in enumerate(orders_data):
        product_id = product_ids[indx][0]
        quantity = quantities[indx][0]
        order_changed = row[0]
        order_id = row[1]
        trailing_price = row[3]
        if order_changed == 'y':
            if order_id != 'n':
                degiro.delete_order(order_id)
                time.sleep(2)
            degiro.sellorder(Order.Type.STOPLOSS, product_id, 3, quantity, None, trailing_price)
            time.sleep(2)
    order_changed_data = np.full((len(product_ids), 1), 'n').tolist()
    order_changed_range = "positions!L2:L"
    sheets_service.setSheetValues(order_changed_range, order_changed_data)


def update_trailing_price():
    login_de_giro()
    trailing_active_data = sheets_service.getSheetValues('positions!R2:R')
    trailing_prices_sheet = sheets_service.getSheetValues('positions!O2:O')
    tickers = sheets_service.getSheetValues('positions!A2:A')
    for indx, row in enumerate(trailing_active_data):
        if len(row) > 0:
            trailing_active = row[0]
            ticker = tickers[indx][0]
            if trailing_active == 'y':
                trailing_price_sheet = trailing_prices_sheet[indx][0]
                position_row = indx + 2
                today = datetime.today()
                trailing_date = today - timedelta(days=3)
                stock_price_data = yf.download(ticker,
                                               start=trailing_date.strftime('%Y-%m-%d'),
                                               end=today.strftime('%Y-%m-%d'),
                                               progress=False)
                trailing_price = '{:.2f}'.format(stock_price_data['Low'][0])
                if trailing_price != trailing_price_sheet:
                    trailing_price_data = [[trailing_price]]
                    trailing_price_range = f"positions!O{position_row}"
                    sheets_service.setSheetValues(trailing_price_range, trailing_price_data)


def login_de_giro():
    try:
        degiro.login(USERNAME, PASSWORD)
    except Exception as e:
        print('Error while trying to login in De Giro')
        print(e)
        return
