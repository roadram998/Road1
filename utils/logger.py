import csv
import logging
import os
from datetime import datetime
import uuid

class Logger:
    def __init__(self):
        # إعداد logger باستخدام logging القياسي
        self.logger = logging.getLogger('MyBotTrader')
        self.logger.setLevel(logging.DEBUG)  # تغيير المستوى إلى DEBUG

        # إنشاء مجلد logs إذا لم يكن موجودًا
        log_dir = "logs"
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except Exception as e:
                print(f"⚠️ Failed to create logs directory: {str(e)}")
                raise

        # إعداد handler لتسجيل الملف
        log_file = os.path.join(log_dir, 'errors.log')
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # تسجيل DEBUG وما فوق في الملف
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(file_handler)

        # إعداد handler للإخراج في الوحدة النصية (console) لـ ERROR فقط
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)  # عرض ERROR فقط على وحدة التحكم
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(console_handler)

        # إعداد ملفات CSV
        self.trade_log_file = "trade_log.csv"
        self.signal_log_file = "signals_log.csv"
        self.session_log_file = "session_log.csv"

        # إعداد ملف trade_log.csv
        with open(self.trade_log_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if file.tell() == 0:  # الملف فارغ
                writer.writerow(["Signal ID", "Timestamp", "Symbol", "Trade Type", "Amount", "Result", "Balance", "Signal Score"])

        # إعداد ملف signals_log.csv
        with open(self.signal_log_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if file.tell() == 0:  # الملف فارغ
                writer.writerow(["Signal ID", "Timestamp", "Symbol", "Trade Time", "Direction", "Signal Score", "Accepted", "Candle Direction", "Candle Confidence"])

        # إعداد ملف session_log.csv
        with open(self.session_log_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if file.tell() == 0:  # الملف فارغ
                writer.writerow(["Session ID", "Start Time", "End Time", "Account Type", "Total Profit", "Total Loss", "Final Balance", "Total Trades", "Wins", "Losses", "Ties", "Stop Reason"])

    def debug(self, message):
        """تسجيل رسالة بمستوى DEBUG في errors.log."""
        self.logger.debug(message)

    def info(self, message):
        """تسجيل رسالة بمستوى INFO في errors.log."""
        self.logger.info(message)

    def warning(self, message):
        """تسجيل رسالة بمستوى WARNING في errors.log والوحدة النصية."""
        self.logger.warning(message)

    def error(self, message):
        """تسجيل رسالة بمستوى ERROR في errors.log والوحدة النصية."""
        self.logger.error(message)

    def log_trade(self, signal_id, symbol, trade_type, amount, result, balance, signal_score=0):
        """تسجيل الصفقة في ملف trade_log.csv مع معرف الإشارة."""
        with open(self.trade_log_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([signal_id, datetime.now().isoformat(), symbol, trade_type, amount, result, balance, signal_score])
        self.info(f"Trade logged: Signal ID={signal_id}, Symbol={symbol}, Type={trade_type}, Amount={amount:.2f}, Result={result}, Balance={balance:.2f}")

    def log_signal(self, symbol, trade_time, direction, signal_score, accepted, candle_direction=None, candle_confidence=None):
        """تسجيل الإشارة في ملف signals_log.csv وإرجاع معرف الإشارة."""
        signal_id = str(uuid.uuid4())  # إنشاء معرف فريد
        with open(self.signal_log_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([signal_id, datetime.now().isoformat(), symbol, trade_time, direction, signal_score, accepted, candle_direction, candle_confidence])
        self.info(f"Signal logged: Signal ID={signal_id}, Symbol={symbol}, Direction={direction}, Accepted={accepted}")
        return signal_id

    def update_session_stats(self):
        """حساب إحصائيات الجلسة من trade_log.csv."""
        total_profit = 0.0
        total_loss = 0.0
        total_trades = 0
        wins = 0
        losses = 0
        ties = 0
        final_balance = 0.0
        initial_balance = 0.0

        if os.path.exists(self.trade_log_file):
            with open(self.trade_log_file, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                trades = list(reader)
                if trades:
                    initial_balance = float(trades[0]["Balance"]) - float(trades[0]["Amount"]) if trades[0]["Result"] == "loss" else float(trades[0]["Balance"])
                    for i, trade in enumerate(trades):
                        amount = float(trade["Amount"])
                        result = trade["Result"]
                        balance = float(trade["Balance"])

                        total_trades += 1
                        if result == "win":
                            wins += 1
                            total_profit += float(trade["Balance"]) - (float(trades[i-1]["Balance"]) if i > 0 else initial_balance)
                        elif result == "loss":
                            losses += 1
                            total_loss += (float(trades[i-1]["Balance"]) if i > 0 else initial_balance) - float(trade["Balance"])
                        elif result == "tie":
                            ties += 1
                    final_balance = float(trades[-1]["Balance"]) if trades else 0.0

        return total_profit, total_loss, final_balance, total_trades, wins, losses, ties, initial_balance

    def log_session(self, start_time, end_time, account_type, net_profit, net_loss, final_balance, total_trades, wins, losses, ties, stop_reason):
        """تسجيل تفاصيل الجلسة في ملف session_log.csv."""
        session_id = str(uuid.uuid4())  # إنشاء معرف فريد للجلسة
        with open(self.session_log_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([session_id, start_time.isoformat(), end_time.isoformat(), account_type, net_profit, net_loss, final_balance, total_trades, wins, losses, ties, stop_reason])
        self.info(
            f"Session logged: Session ID={session_id}, Start={start_time.isoformat()}, End={end_time.isoformat()}, "
            f"AccountType={account_type}, NetProfit={net_profit:.2f}, NetLoss={net_loss:.2f}, "
            f"FinalBalance={final_balance:.2f}, TotalTrades={total_trades}, Wins={wins}, "
            f"Losses={losses}, Ties={ties}, Reason={stop_reason}"
        )