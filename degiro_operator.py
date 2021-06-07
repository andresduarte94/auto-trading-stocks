import time
import degiroapi
import numpy as np
from degiroapi.order import Order
from datetime import datetime, timedelta
from degiroapi.product import Product
from google.cloud import secretmanager_v1beta1 as secretmanager
import sheets_service

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
    values = sheets_service.getSheetValues('positions!A2:N')
    for indx, row in enumerate(values):
        stop_loss = float(row[2])
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
        sl_trigger = (current_price - stop_loss) * 100 / current_price
        tp_trigger = (take_profit - current_price) * 100 / current_price
        print(row[0])
        print(current_price)
        print(stop_loss)
        print(take_profit)
        print(" ")
        print(sl_trigger)
        print(tp_trigger)
        if 15 > sl_trigger > 0:
            print('sl trigger')
            create_sell_order(product_id, 'SL', quantity, stop_loss, close_order, order_changed, order_id)
        elif 15 > tp_trigger > 0:
            print('tp trigger')
            create_sell_order(product_id, 'TP', quantity, take_profit, close_order, order_changed, order_id)
        elif tp_trigger < 0 or sl_trigger < 0:
            print('Sold at market order, due to SL or TP breached')
            degiro.sellorder(Order.Type.MARKET, product_id, 3, quantity)
            market_order = 'TP' if tp_trigger < 0 else 'SL'
            market_order_data = [[market_order]]
            row_number = indx + 2
            market_order_range = f"positions!K{row_number}"
            market_order_values = {'range': market_order_range, 'values': market_order_data}
            sheets_service.setSheetValues(market_order_range, market_order_values)
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
                time.sleep(5)
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
            time.sleep(5)
        elif order_type == 'TP':
            degiro.sellorder(Order.Type.LIMIT, product_id, 3, quantiy, price)
            time.sleep(5)
    except Exception as e:
        print('Error while trying to place sell order for product ID: ' + str(product_id))
        print(e)
    print(order_type + ' order placed')


def update_sheets_data():
    values = sheets_service.getSheetValues('positions!A2:K')
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
    data_size = sheets_service.get_last_row('positions!A1:D') - 1
    order_data = np.full((data_size, 4), 'n').tolist()
    quantity_data = np.full((data_size, 6), 'n').tolist()
    rows_to_delete = []
    for indx, row in enumerate(values):
        sheets_product_id = row[1]
        sl_sheet = float(row[2])
        tp_sheet = float(row[3])
        last_position = len(portfolio) - 1
        for port_indx, position in enumerate(portfolio):
            row_number = indx + 2
            if position['id'] == sheets_product_id:
                # Fill quantity and entry_price sheets data
                quantity_data[indx][0] = position['size']
                quantity_data[indx][1] = f'=E{row_number}*G{row_number}*GOOGLEFINANCE("CURRENCY:USDEUR")'
                quantity_data[indx][2] = position['breakEvenPrice']
                quantity_data[indx][3] = f"=(D{row_number}-G{row_number})*F{row_number}*0.99/G{row_number}"
                quantity_data[indx][4] = f"=(C{row_number}-G{row_number})*F{row_number}*1.01/G{row_number}"
                quantity_data[indx][5] = f"=ABS(H{row_number}/I{row_number})"
                break
            if port_indx == last_position:
                # Get P/L depending on last sell order placed
                close_order = row[10]
                profit = row[7]
                loss = row[8]
                p_l = profit if close_order == 'TP' else loss
                # Set closed position values to positions_history table
                position_history_row = sheets_service.get_last_row('positions_history!A1:B') + 1
                history_range = f"positions_history!A{position_history_row}:L{position_history_row}"
                history_row = row[:10]
                history_row.append(p_l)
                history_row.append(datetime.today().strftime('%Y-%m-%d'))
                history_data = [history_row]
                history_values = {'range': history_range, 'values': history_data}
                sheets_service.setSheetValues(history_range, history_values)
                # Add row index to delete rows array
                rows_to_delete.append(indx + 1)
        for order in orders:
            if str(order['productId']) == sheets_product_id:
                if order['isActive'] and order['buysell'] == 'S':
                    # Check if indx is in rows_to_delete, if it is then cancel order with order_id
                    if indx in rows_to_delete:
                        try:
                            degiro.delete_order(order['orderId'])
                            time.sleep(5)
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
                            if sl_sheet != order['stopPrice']:
                                order_data[indx][1] = 'y'
                    break
    # Set orders information into sheet
    order_range = 'positions!K2:N'
    order_body = {'range': order_range, 'values': order_data}
    sheets_service.setSheetValues(order_range, order_body)
    # Set quantity, size and entry_price values
    quantity_range = 'positions!E2:J'
    quantity_body = {'range': quantity_range, 'values': quantity_data}
    sheets_service.setSheetValues(quantity_range, quantity_body)
    # Delete rows with old positions, this must be the last sheet operation
    sheets_service.delete_positions_rows(rows_to_delete, '427440165', 14)
    print('Sheets are updated')


def insert_new_positions():
    pending_orders = sheets_service.getSheetValues('pending_orders!B2:B')
    product_ids = sheets_service.getSheetValues('positions!B2:B')
    try:
        portfolio = degiro.getdata(degiroapi.Data.Type.PORTFOLIO, True)
    except Exception as e:
        print('Error while trying to get portafolio data')
        print(e)
        return
    rows_to_delete = []
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
                    pending_order_data = [
                        [pending_order_values[0][0], pending_order_values[0][1], pending_order_values[0][6],
                         pending_order_values[0][7]]]
                    # Set values on position table
                    position_row = sheets_service.get_last_row('positions!A1:B') + 1
                    new_position_range = f"positions!A{position_row}:D{position_row}"
                    new_position_values = {'range': new_position_range, 'values': pending_order_data}
                    sheets_service.setSheetValues(new_position_range, new_position_values)
                    print(f"Pending order of row number {pending_order_row} has been inserted")
                    # Add row index to delete rows array
                    rows_to_delete.append(indx + 1)
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
    product_id_body = {'range': product_id_range, 'values': product_id_data}
    sheets_service.setSheetValues(product_id_range, product_id_body)
    degiro.logout()


def place_buy_orders():
    login_de_giro()
    buy_data = sheets_service.getSheetValues('risk_management!B2:C')
    entry_prices = sheets_service.getSheetValues('risk_management!F2:F')
    for indx, row in enumerate(buy_data):
        product_id = row[0]
        quantity = row[1]
        price_limit = entry_prices[indx][0]
        try:
            degiro.buyorder(Order.Type.LIMIT, product_id, 3, quantity, price_limit)
            time.sleep(5)
        except Exception as e:
            print('Error while trying to place buy order for product ID: ' + product_id)
            print(e)
    degiro.logout()


def login_de_giro():
    try:
        degiro.login(USERNAME, PASSWORD)
    except Exception as e:
        print('Error while trying to login in De Giro')
        print(e)
        return
