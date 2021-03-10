import time
from flask import Flask, Response
from degiro_operator import attempt_trade_degiro, get_stocks_info, place_buy_orders
from ftx_operator import buy_sl_orders_ftx, place_tp_orders_ftx
from threading import Thread

app = Flask(__name__)
run_auto_trade = False
message = ''


@app.route('/')
def hello():
    return 'Hello to the Auto-Trading Stocks application!'


# Endpoints for De Giro Stocks trading
@app.route('/start')
def start_auto_trade():
    global run_auto_trade
    run_auto_trade = True
    return Response(run_process(), mimetype="text/html")


@app.route('/stop')
def stop_auto_trade():
    global run_auto_trade
    run_auto_trade = False
    return "Application stopped"


@app.route('/stocks_info')
def stocks_info():
    get_stocks_info()
    return 'Product IDs have been updated'


@app.route('/buy_orders')
def buy_orders():
    place_buy_orders()
    return 'Buy orders have been placed'


def record_loop():
    global run_auto_trade, message
    while run_auto_trade:
        message = attempt_trade_degiro()
        print(message)
        time.sleep(60*5)


def run_process():
    t = Thread(target=record_loop)
    t.start()
    return 'Processing... :' + message


# Endpoints for FTX Crypto trading
@app.route('/set_orders_ftx')
def set_orders_ftx():
    buy_sl_orders_ftx()
    return 'Buy and SL orders have been placed'


@app.route('/place_tp_ftx')
def place_tp_ftx():
    place_tp_orders_ftx()
    return 'TP orders have been placed'


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True, use_reloader=False)

