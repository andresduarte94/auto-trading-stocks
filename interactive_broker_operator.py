from ibapi.client import EClient
from ibapi.common import OrderId
from ibapi.order_state import OrderState
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import *

import sheets_service

import threading
import time


app = None


class IBapi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.portafolio = []

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
        if isinstance(app.nextorderId, int):
            app.nextorderId = app.nextorderId + 1
        order.contract = contract

    def orderStatus(self, orderId: OrderId, status: str, filled: float, remaining: float, avgFillPrice: float,
                    permId: int, parentId: int, lastFillPrice: float, clientId: int, whyHeld: str, mktCapPrice: float):
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId,
                            whyHeld, mktCapPrice)
        print("OrderStatus. Id:", orderId, "Status:", status, "Filled:", filled, "Remaining:", remaining,
              "AvgFillPrice:", avgFillPrice, "PermId:", permId, "ParentId:", parentId, "LastFillPrice:", lastFillPrice,
              "ClientId:", clientId, "WhyHeld:", whyHeld, "MktCapPrice:", mktCapPrice)

    def openOrderEnd(self):
        super().openOrderEnd()
        print("OpenOrderEnd")
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
    product_ids = sheets_service.getSheetValues('positions!B2:B')
    quantity_data = []
    pl_data = []
    # rows_to_delete = []
    for indx, row in enumerate(product_ids):
        product_id = row[0]
        row_number = indx + 2
        for port_indx, position in enumerate(portfolio):
            if product_id == str(position['stock_id']):
                # Fill quantity and entry_price sheets data
                entry_size = f'=E{row_number}*G{row_number}*GOOGLEFINANCE("CURRENCY:USDEUR")'
                profit = f"=(D{row_number}-G{row_number})*F{row_number}/G{row_number}"
                loss = f"=(C{row_number}-G{row_number})*F{row_number}/G{row_number}"
                r_const = f"=ABS(H{row_number}/I{row_number})"
                quantity_data.append([position['symbol'], position['stock_id'], None, None, position['size'],
                                      entry_size, position["avg_cost"], profit, loss, r_const])
                trailing_pl = f"=(O{row_number}-G{row_number})*F{row_number}/G{row_number}"
                current_pl = f'=(GOOGLEFINANCE(A{row_number},"price")-G{row_number})*F{row_number}/G{row_number}'
                pl_data.append([trailing_pl, current_pl])
    # Set quantity, size and entry_price values
    quantity_range = 'positions!A2:J'
    sheets_service.setSheetValues(quantity_range, quantity_data)
    # Set trailing and current P/L
    pl_range = 'positions!P2:Q'
    sheets_service.setSheetValues(pl_range, pl_data)


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
        # stop_loss = positions[indx][2]
        take_profit = positions[indx][3]
        quantity = positions[indx][4]
        if sl_order_id == 'n' or sl_order_price != trailing_price:
            new_sl_order_id = app.nextorderId if sl_order_id == 'n' else sl_order_id
            order_row[0] = new_sl_order_id
            order_row[1] = trailing_price
            contract = get_stock_contract(symbol)
            order = get_stock_order('SELL', quantity, 'STP', trailing_price)
            app.placeOrder(new_sl_order_id, contract, order)
            app.nextorderId = app.nextorderId + 1
        if tp_order_id == 'n' or tp_order_price != take_profit:
            new_tp_order_id = app.nextorderId if tp_order_id == 'n' else tp_order_id
            order_row[2] = new_tp_order_id
            order_row[3] = take_profit
            contract = get_stock_contract(symbol)
            order = get_stock_order('SELL', quantity, 'LMT', take_profit)
            app.placeOrder(new_tp_order_id, contract, order)
            app.nextorderId = app.nextorderId + 1
        order_data.append(order_row)
    # Set orders information into sheet
    order_range = 'positions!K2:O'
    sheets_service.setSheetValues(order_range, order_data)


def trigger_orders_ib():
    global app
    app = IBapi()
    app.connect('127.0.0.1', 7496, 123)
    app.nextorderId = None
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
    app.reqAllOpenOrders()
    # Request open positions
    app.reqPositions()
    # Wait for data to be filled
    time.sleep(5)
    # Update positions data and place/update orders if needed
    update_positions_data(app.portafolio)
    place_tp_sl_orders()
    # Disconect from TWS app
    app.disconnect()


if __name__ == '__main__':
    trigger_orders_ib()
