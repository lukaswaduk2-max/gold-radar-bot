import datetime
import os
import threading
import time
from flask import Flask
import numpy as np
import pandas as pd
import requests
import yfinance as yf

app = Flask(__name__)

BOT_TOKEN = "8924246395:AAGWRIM4ACKCZPSf-bx00km53kEPruPFT-g"
CHAT_ID = "1341180745"
MODAL = 1000.0
RISK_PERCENT = 0.02
RR_RATIO = 3.0
SPREAD_BUFFER = 0.50


def kirim_telegram(pesan):
  try:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": pesan}, timeout=10)
  except Exception as e:
    print(f"Gagal kirim telegram: {e}")


def hitung_lot(jarak_sl, modal, risk_pct):
  risk_dollar = modal * risk_pct
  lot = risk_dollar / (jarak_sl * 100)
  return max(0.01, round(lot, 2))


def radar_loop():
  print("Background Radar XAUUSD dimulai...")
  pesan_start = (
      "🚀 [SERVER CLOUD AKTIF 24/7]\n"
      "• Instrumen : XAUUSD (Gold)\n"
      "• Strategi  : M15 CHoCH + M5 FVG Retest\n"
      "• Parameter : RR 1:3 | Maks 1 Trade/Hari\n"
      "• Server    : Standby di Cloud Nonstop"
  )
  kirim_telegram(pesan_start)

  last_signal_date = None
  active_bias = None
  bias_time = None
  active_gap = None

  while True:
    try:
      now_utc = datetime.datetime.now(datetime.timezone.utc)
      today_str = str(now_utc.date())

      # Istirahat jika akhir pekan (Sabtu & Minggu bursa tutup)
      if now_utc.weekday() in [5, 6]:
        time.sleep(1800)
        continue

      # Jika hari ini sudah ada 1 sinyal tereksekusi, tunggu pergantian hari
      if last_signal_date == today_str:
        time.sleep(300)
        continue

      # 1. Unduh data M15 dan M5
      df_m15 = yf.download("GC=F", period="5d", interval="15m", progress=False)
      if isinstance(df_m15.columns, pd.MultiIndex):
        df_m15.columns = df_m15.columns.get_level_values(0)
      df_m15 = df_m15.dropna().copy()

      df_m5 = yf.download("GC=F", period="2d", interval="5m", progress=False)
      if isinstance(df_m5.columns, pd.MultiIndex):
        df_m5.columns = df_m5.columns.get_level_values(0)
      df_m5 = df_m5.dropna().copy()

      # 2. Cek M15 CHoCH + Lonjakan Volume
      df_m15["Swing_H"] = df_m15["High"].shift(1).rolling(16).max()
      df_m15["Swing_L"] = df_m15["Low"].shift(1).rolling(16).min()
      df_m15["Vol_MA"] = df_m15["Volume"].rolling(20).mean()

      last_m15 = df_m15.iloc[-1]
      m15_time = df_m15.index[-1]

      if (
          last_m15["Close"] > last_m15["Swing_H"]
          and last_m15["Close"] > last_m15["Open"]
          and last_m15["Volume"] > last_m15["Vol_MA"]
      ):
        active_bias = "BULLISH"
        bias_time = m15_time
      elif (
          last_m15["Close"] < last_m15["Swing_L"]
          and last_m15["Close"] < last_m15["Open"]
          and last_m15["Volume"] > last_m15["Vol_MA"]
      ):
        active_bias = "BEARISH"
        bias_time = m15_time

      if bias_time and (m15_time - bias_time).total_seconds() > 10800:
        active_bias = None
        active_gap = None

      # 3. Deteksi Gap M5 Baru
      if len(df_m5) >= 3 and active_bias:
        c1 = df_m5.iloc[-3]
        c3 = df_m5.iloc[-1]
        if active_bias == "BULLISH" and c3["Low"] > c1["High"]:
          active_gap = {"type": "BUY", "top": c3["Low"], "bottom": c1["High"]}
        elif active_bias == "BEARISH" and c3["High"] < c1["Low"]:
          active_gap = {
              "type": "SELL",
              "top": c1["Low"],
              "bottom": c3["High"],
          }

      # 4. Trigger Entry Saat Retest Gap
      if active_gap and last_signal_date != today_str:
        curr_m5 = df_m5.iloc[-1]

        if active_gap["type"] == "BUY" and curr_m5["Low"] <= active_gap["top"]:
          entry = active_gap["top"]
          sl = active_gap["bottom"] - SPREAD_BUFFER
          jarak_sl = entry - sl
          if jarak_sl > 0.40:
            tp = entry + (jarak_sl * RR_RATIO)
            lot = hitung_lot(jarak_sl, MODAL, RISK_PERCENT)
            sinyal = (
                "🚨 [SINYAL CLOUD: BUY XAUUSD]\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Aksi       : BUY (Retest M5 Gap)\n"
                "• Konfirmasi : M15 CHoCH Valid\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"• Entry      : {entry:.2f}\n"
                f"• Stop Loss  : {sl:.2f} (Jarak: ${jarak_sl:.2f})\n"
                f"• Take Profit: {tp:.2f} (RR 1:3)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"• Rekomendasi: {lot} Lot (Risk 2% = $20)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ Limit 1 Trade hari ini aktif."
            )
            kirim_telegram(sinyal)
            last_signal_date = today_str
            active_gap = None
            active_bias = None

        elif (
            active_gap["type"] == "SELL"
            and curr_m5["High"] >= active_gap["bottom"]
        ):
          entry = active_gap["bottom"]
          sl = active_gap["top"] + SPREAD_BUFFER
          jarak_sl = sl - entry
          if jarak_sl > 0.40:
            tp = entry - (jarak_sl * RR_RATIO)
            lot = hitung_lot(jarak_sl, MODAL, RISK_PERCENT)
            sinyal = (
                "🚨 [SINYAL CLOUD: SELL XAUUSD]\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Aksi       : SELL (Retest M5 Gap)\n"
                "• Konfirmasi : M15 CHoCH Valid\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"• Entry      : {entry:.2f}\n"
                f"• Stop Loss  : {sl:.2f} (Jarak: ${jarak_sl:.2f})\n"
                f"• Take Profit: {tp:.2f} (RR 1:3)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"• Rekomendasi: {lot} Lot (Risk 2% = $20)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ Limit 1 Trade hari ini aktif."
            )
            kirim_telegram(sinyal)
            last_signal_date = today_str
            active_gap = None
            active_bias = None

      time.sleep(60)
    except Exception as e:
      print(f"Error loop: {e}")
      time.sleep(30)


# Jalankan thread radar saat aplikasi web hidup
threading.Thread(target=radar_loop, daemon=True).start()


@app.route("/")
def home():
  return "Radar XAUUSD Server is RUNNING 24/7!"


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)
