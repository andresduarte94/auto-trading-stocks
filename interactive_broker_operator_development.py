from ibapi.client import EClient
from ibapi.common import OrderId
from ibapi.order_state import OrderState
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import *

import sheets_service

import threading
import time
from datetime import datetime, timedelta

app = None


class IBapi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.portafolio = []
        self.nextorderId = None
        self.orders = []

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextorderId = orderId
        print('The next valid order id is: ', self.nextorderId)

    def execDetails(self, reqId, contract, execution):
        print('Order Executed: ', reqId, contract.symbol, contract.secType, contract.currency, execution.execId,
              execution.orderId, execution.shares, execution.lastLiquidity)

    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        super().position(account, contract, position, avgCost)
        print("Position.", "Account:", account, "Symbol:", contract.symbol, "SecType:", contract.secType, "Currency:",
              contract.currency, "Position:", position, "Avg cost:", avgCost, "ID:", contract.conId)
        self.portafolio.append({"symbol": contract.symbol, "size": position, "avg_cost": avgCost,
                                "stock_id": contract.conId})

    def positionEnd(self):
        super().positionEnd()
        print("PositionEnd")

    def openOrder(self, orderId: OrderId, contract: Contract, order: Order, orderState: OrderState):
        super().openOrder(orderId, contract, order, orderState)
        print("OpenOrder. PermId: ", order.permId, "ClientId:", order.clientId, " OrderId:", orderId,
              "Account:", order.account, "Symbol:", contract.symbol, "SecType:", contract.secType,
              "Exchange:", contract.exchange, "Action:", order.action, "OrderType:", order.orderType,
              "TotalQty:", order.totalQuantity, "CashQty:", order.cashQty, "LmtPrice:", order.lmtPrice,
              "AuxPrice:", order.auxPrice, "Status:", orderState.status)
        order.contract = contract
        self.orders.append({"symbol": contract.symbol, "OrderType": order.orderType})

    def orderStatus(self, orderId: OrderId, status: str, filled: float, remaining: float, avgFillPrice: float,
                    permId: int, parentId: int, lastFillPrice: float, clientId: int, whyHeld: str, mktCapPrice: float):
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId,
                            whyHeld, mktCapPrice)
        print("OrderStatus. Id:", orderId, "Status:", status, "Filled:", filled, "Remaining:", remaining,
              "AvgFillPrice:", avgFillPrice, "PermId:", permId, "ParentId:", parentId, "LastFillPrice:", lastFillPrice,
              "ClientId:", clientId, "WhyHeld:", whyHeld, "MktCapPrice:", mktCapPrice)

    def openOrderEnd(self):
        super().openOrderEnd()
        # print("OpenOrderEnd")
        # logging.debug("Received %d openOrders", len(self.permId2ord))


def run_loop():
    app.run()


# Function to create stock Order contract
def get_stock_contract(symbol):
    contract = Contract()
    contract.symbol = symbol
    contract.secType = 'STK'
    contract.exchange = 'SMART'
    contract.currency = 'USD'
    contract.primaryExchange = "ISLAND"
    return contract


# Function to create stock Order contract
def get_stock_order(action, quantity, orderType, price):
    order = Order()
    order.tif = 'GTC'
    order.action = action
    order.totalQuantity = quantity
    order.orderType = orderType
    if orderType == 'LMT':
        order.lmtPrice = price
    if orderType == 'STP':
        order.auxPrice = price
    return order


# Update stock info, size, entry price and TP, SL, R
def update_positions_data(portfolio):
    global app
    stocks_data = sheets_service.getSheetValues('positions!A2:P')
    quantity_data = []
    rows_to_delete = []
    history_data = []
    for indx, row in enumerate(stocks_data):
        ticker = row[0]
        row_number = indx + 2
        isPositionClosed = True
        # Iterate through portfolio to update stocks data
        for port_indx, position in enumerate(portfolio):
            if ticker == str(position['symbol']) and position['size'] != 0.0:
                # Fill quantity and entry_price sheets data
                entry_size = f'=E{row_number}*G{row_number}*GOOGLEFINANCE("CURRENCY:USDEUR")'
                profit = f"=(D{row_number}-G{row_number})*F{row_number}/G{row_number}"
                loss = f"=(C{row_number}-G{row_number})*F{row_number}/G{row_number}"
                r_const = f"=ABS(H{row_number}/I{row_number})"
                trailing_pl = f"=(O{row_number}-G{row_number})*F{row_number}/G{row_number}"
                current_pl = f'=(GOOGLEFINANCE(A{row_number},"price")-G{row_number})*F{row_number}/G{row_number}'
                quantity_data.append([position['symbol'], position['stock_id'], None, None, position['size'],
                                      entry_size, position['avg_cost'], profit, loss, r_const, None, None, None, None,
                                      None, trailing_pl, current_pl])
                isPositionClosed = False
                break
        if isPositionClosed:
            quantity_data.append([None]*17)
            # Get P/L depending on open order
            symbol = row[0]
            openOrder = next((order for order in app.orders if order['symbol'] == symbol), {'OrderType': 'LMT'})
            profit = row[7]
            loss = row[15]
            p_l = loss if openOrder['OrderType'] == 'LMT' else profit
            history_row = row[:10]
            history_row.append(p_l)
            history_row.append(datetime.today().strftime('%Y-%m-%d'))
            history_data.append(history_row)
            # Add row index to delete rows array
            rows_to_delete.append(indx + 1)
            # Cancel unused order
            cancelOrderId = row[12] if openOrder['OrderType'] == 'LMT' else row[10]
            app.cancelOrder(cancelOrderId)
    # Set quantity, size and entry_price values
    quantity_range = 'positions!A2:Q'
    sheets_service.setSheetValues(quantity_range, quantity_data)
    # Set position history information
    positions_history_row = sheets_service.get_last_row('positions_history!A1:A') + 1
    history_range = f'positions_history!A{positions_history_row}:L'
    sheets_service.setSheetValues(history_range, history_data)
    # Delete rows with old positions, this must be the last sheet operation
    time.sleep(1)
    sheets_service.delete_positions_rows(rows_to_delete, '427440165', 19)
    print('Sheets are updated')


def place_tp_sl_orders():
    global app
    current_orders = sheets_service.getSheetValues('positions!K2:O')
    positions = sheets_service.getSheetValues('positions!A2:E')
    order_data = []
    for indx, order_row in enumerate(current_orders):
        sl_order_id = order_row[0]
        sl_order_price = order_row[1]
        tp_order_id = order_row[2]
        tp_order_price = order_row[3]
        trailing_price = order_row[4]
        symbol = positions[indx][0]
        take_profit = positions[indx][3]
        quantity = positions[indx][4]
        if sl_order_id == 'n' or sl_order_price != trailing_price:
            new_sl_order_id = app.nextorderId if sl_order_id == 'n' else sl_order_id
            order_row[0] = new_sl_order_id
            order_row[1] = trailing_price
            contract = get_stock_contract(symbol)
            order = get_stock_order('SELL', quantity, 'STP', trailing_price)
            app.placeOrder(new_sl_order_id, contract, order)
            app.nextorderId = (app.nextorderId + 1) if sl_order_id == 'n' else app.nextorderId
        if tp_order_id == 'n' or tp_order_price != take_profit:
            new_tp_order_id = app.nextorderId if tp_order_id == 'n' else tp_order_id
            order_row[2] = new_tp_order_id
            order_row[3] = take_profit
            contract = get_stock_contract(symbol)
            order = get_stock_order('SELL', quantity, 'LMT', take_profit)
            app.placeOrder(new_tp_order_id, contract, order)
            app.nextorderId = (app.nextorderId + 1) if tp_order_id == 'n' else app.nextorderId
        order_data.append(order_row)
    # Set orders information into sheet
    order_range = 'positions!K2:O'
    sheets_service.setSheetValues(order_range, order_data)


def place_buy_orders():
    global app
    stocks_data = sheets_service.getSheetValues('positions!A2:E')
    for row in stocks_data:
        stock_ticker = row[0]
        stock_quantity = row[4]
        new_order_id = app.nextorderId
        print('orderID: ' + str(app.nextorderId))
        stock_contract = get_stock_contract(stock_ticker)
        stock_order = get_stock_order('BUY', stock_quantity, 'MKT', 0)
        app.placeOrder(new_order_id, stock_contract, stock_order)
        app.nextorderId = app.nextorderId + 1
        time.sleep(2)


def place_order_test():
    global app
    '''
    new_order_id = app.nextorderId
    print('orderID: ' + str(new_order_id))
    contract = get_stock_contract('DIS')
    order = get_stock_order('BUY', 1, 'LMT', 130.0)
    app.placeOrder(new_order_id, contract, order)
    app.nextorderId = app.nextorderId + 1
    time.sleep(5)
    '''


def trigger_orders_ib():
    global app
    app = IBapi()
    app.connect('127.0.0.1', 7496, 123)
    # Start the socket in a thread
    api_thread = threading.Thread(target=run_loop, daemon=True)
    api_thread.start()
    time.sleep(5)
    # Check if the API is connected via orderid
    while True:
        if isinstance(app.nextorderId, int):
            print('connected')
            state = 'connected'
            break
        else:
            print('waiting for connection')
            state = 'waiting for connection'
            time.sleep(1)

    # Cancel all open orders
    # app.reqGlobalCancel()
    # Request open orders
    # app.reqAllOpenOrders()

    # Place buy market orders
    # place_buy_orders()

    # '''
    # Request open positions
    app.reqPositions()
    # Wait for data to be filled
    time.sleep(5)

    # Update positions data and place/update orders if needed
    update_positions_data(app.portafolio)
    time.sleep(1)
    place_tp_sl_orders()
    # '''

    # Test function
    # place_order_test()

    # Disconect from TWS app
    app.disconnect()


if __name__ == '__main__':
    trigger_orders_ib()

