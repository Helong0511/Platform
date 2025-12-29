import tkinter as tk
import requests

API = "http://127.0.0.1:8000/order"

def hedge():
    symbol = symbol_var.get()
    lot = float(lot_var.get())

    for cmd in ("BUY", "SELL"):
        requests.post(API, json={
            "cmd": cmd,
            "symbol": symbol,
            "volume": lot
        }, timeout=2)

root = tk.Tk()
root.title("真实对冲下单")

symbol_var = tk.StringVar(value="EURUSD")
lot_var = tk.StringVar(value="0.01")

tk.Label(root, text="品种").pack()
tk.Entry(root, textvariable=symbol_var).pack()

tk.Label(root, text="手数").pack()
tk.Entry(root, textvariable=lot_var).pack()

tk.Button(root, text="真实 买 + 卖", bg="red", fg="white",
          height=2, command=hedge).pack(pady=15)

root.mainloop()
