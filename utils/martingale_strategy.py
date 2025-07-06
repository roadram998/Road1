import logging

# إعدادات التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('errors.log', mode='a', encoding='utf-8')
    ]
)

# إضافة معالج لعرض رسائل ERROR فقط على وحدة التحكم
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logging.getLogger().addHandler(console_handler)

class MartingaleStrategy:
    def __init__(self, settings, initial_balance):
        max_loss_count = settings.get("max_loss_count", 4)
        try:
            float_value = float(max_loss_count)
            if not float_value.is_integer():
                raise ValueError(f"max_loss_count يجب أن يكون عددًا صحيحًا، القيمة المقدمة: {max_loss_count}")
            max_loss_count = int(float_value)
        except (ValueError, TypeError) as e:
            logging.error(f"خطأ في max_loss_count: {str(e)}")
            raise ValueError(f"max_loss_count غير صالح: {str(e)}")

        self.settings = {
            "amount": float(settings.get("amount", 1.0)),
            "multiplier": float(settings.get("multiplier", 2.0)),
            "profit": float(settings.get("profit", 0.0)),
            "loss": float(settings.get("loss", 0.0)),
            "max_loss_count": max_loss_count,
            "payout": float(settings.get("payout", 70.0))
        }
        self.initial_balance = float(initial_balance)
        self.current_balance = float(initial_balance)
        self.current_amount = float(self.settings["amount"])
        self.loss_count = 0
        self.is_active = True
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.total_trades = 0
        logging.info(f"تهيئة MartingaleStrategy مع max_loss_count: {self.settings['max_loss_count']}")

    def get_amount(self):
        """إرجاع المبلغ الحالي للصفقة."""
        return self.current_amount

    def update_balance(self, new_balance: float):
        """تحديث الرصيد المخزن مؤقتًا."""
        self.current_balance = float(new_balance)

    async def update_amount(self, result: str, amount: float, profit_or_loss: float, payout: float):
        """تحديث المبلغ بناءً على نتيجة الصفقة."""
        try:
            self.total_trades += 1
            net_profit = self.current_balance - self.initial_balance
            net_loss = self.initial_balance - self.current_balance if self.current_balance < self.initial_balance else 0

            if net_profit >= self.settings["profit"]:
                logging.info(f"Target profit reached: {net_profit:.2f} >= {self.settings['profit']:.2f}")
                print(f"🟢 Target profit reached ({net_profit:.2f}) – Bot has stopped running!")
                self.is_active = False
                return False
            if net_loss >= self.settings["loss"]:
                logging.info(f"Loss limit reached: {net_loss:.2f} >= {self.settings['loss']:.2f}")
                print(f"🔴 Loss limit reached ({net_loss:.2f}) – Bot has stopped running!")
                self.is_active = False
                return False

            if result == "win":
                self.wins += 1
                self.current_amount = self.settings["amount"]
                self.loss_count = 0
                expected_profit = amount * self.settings["payout"] / 100
                if abs(profit_or_loss - expected_profit) > 0.01:
                    logging.warning(f"الربح المستلم ({profit_or_loss:.2f}) لا يتطابق مع المتوقع ({expected_profit:.2f})")
                logging.info(f"إعادة تعيين المبلغ إلى {self.current_amount:.2f} بعد الفوز، الربح: {profit_or_loss:.2f}")
                return False  # التوقف لانتظار إشارة جديدة
            elif result == "loss":
                self.losses += 1
                self.loss_count += 1
                if self.loss_count < self.settings["max_loss_count"]:
                    self.current_amount *= self.settings["multiplier"]
                    logging.info(f"زيادة المبلغ إلى {self.current_amount:.2f} بعد الخسارة، عدد الخسارات: {self.loss_count}")
                    return True
                else:
                    self.current_amount = self.settings["amount"]
                    logging.info(f"توقف مؤقت بعد الوصول إلى الحد الأقصى للخسارات ({self.settings['max_loss_count']})، المبلغ: {self.current_amount:.2f}")
                    return False
            elif result == "tie":
                self.ties += 1
                self.current_amount = self.settings["amount"]
                self.loss_count = 0
                logging.info(f"إعادة تعيين المبلغ إلى {self.current_amount:.2f} بعد التعادل")
                return False  # التوقف لانتظار إشارة جديدة
        except Exception as e:
            logging.error(f"Error while updating amount: {str(e)}")
            print(f"⚠️ Error while updating amount: {str(e)}")
            self.is_active = False
            return False
        finally:
            logging.info(f"حالة الروبوت: is_active={self.is_active}, loss_count={self.loss_count}, current_amount={self.current_amount:.2f}")