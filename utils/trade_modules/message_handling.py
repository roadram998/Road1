import asyncio
import logging
import os
from datetime import datetime, timedelta
from BinaryOptionsToolsV2.pocketoption.asyncronous import PocketOptionAsync
from ..martingale_strategy import MartingaleStrategy
from ..logger import Logger
from .trade_execution import safe_execute_trade
from .trade_preparation import prepare_trade
from .trade_utils import display_account_stats, check_payout
import pytz
import time
import sys
import msvcrt
import platform

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

async def wait_for_result(client: PocketOptionAsync, trade_id: str, duration: int):
    start_wait = time.time()
    await asyncio.sleep(max(duration - 1, 0))
    max_attempts = 20
    attempt = 0
    failed_parse_duration_count = 0

    while attempt < max_attempts:
        try:
            trade_data = await client.check_win(trade_id)
            if trade_data and "result" in trade_data:
                logging.info(f"نتيجة الصفقة {trade_id}: {trade_data['result']} في {time.strftime('%H:%M:%S')}")
                logging.info(f"Wait time for result: {(time.time() - start_wait):.3f} seconds")
                return trade_data
        except Exception as e:
            err_str = str(e)
            if "Failed to parse duration" in err_str:
                failed_parse_duration_count += 1
                logging.warning(f"⚠️ تجاهل خطأ تحويل المدة (محاولة {attempt+1}): {err_str}")
                if failed_parse_duration_count > 5:
                    await asyncio.sleep(1.0)
                else:
                    await asyncio.sleep(0.5)
            else:
                logging.error(f"محاولة {attempt + 1}/{max_attempts} - خطأ أثناء انتظار نتيجة الصفقة {trade_id}: {err_str}")
                await asyncio.sleep(0.5)
            attempt += 1
            continue
        attempt += 1
        await asyncio.sleep(0.5)

    logging.error(f"فشل جلب نتيجة الصفقة {trade_id} بعد {max_attempts} محاولات")
    return None

def check_for_skip(timeout=0.01):
    """التحقق مما إذا ضغط المستخدم على مفتاح 's' لتخطي الصفقة."""
    if platform.system() == "Windows":
        start_time = time.time()
        while time.time() - start_time < timeout:
            if msvcrt.kbhit():
                key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                return key == 's'
    return False

async def handle_signal(client: PocketOptionAsync, message: dict, strategy: MartingaleStrategy, logger: Logger, ssid=None, demo=None):
    start_total_time = time.time()
    try:
        if not strategy.is_active:
            logging.info("⚠️ الروبوت متوقف، تجاهل الإشارة")
            print("⚠️ الروبوت متوقف، تجاهل الإشارة")
            return

        os.system('cls' if os.name == 'nt' else 'clear')
        symbol = message.get('symbol')
        trade_time = message.get('duration')
        trade_time_exact = message.get('time')
        direction = message.get('direction')

        if not all([symbol, trade_time, direction]):
            logging.error(f"بيانات الإشارة غير مكتملة: {message}")
            print(f"❌ Not Signal : {message}")
            signal_id = logger.log_signal(symbol, trade_time, direction, signal_score=0, accepted=False)
            net_profit = strategy.current_balance - strategy.initial_balance
            net_loss = strategy.initial_balance - strategy.current_balance if strategy.current_balance < strategy.initial_balance else 0
            print(f"💰 Profit: {net_profit:.2f}, Loss: {net_loss:.2f}, Balance: {strategy.current_balance:.2f}")
            return

        # جلب نسبة العائد
        api_symbol, payout = await check_payout(client, symbol, strategy.settings["payout"])
        payout_display = f"{payout:.0f}%" if payout is not None else "N/A"
        direction_display = "🟢 call" if direction.lower() == "call" else "🔴 put"
        print(f"💷 {symbol} {payout_display}\n")
        print(f"💎 {trade_time}\n")
        print(f"⌚️ {trade_time_exact}\n")
        print(f"{direction_display}\n")
        print(f"💶 Amount: {strategy.get_amount():.2f}\n")

        if api_symbol is None:
            signal_id = logger.log_signal(symbol, trade_time, direction, signal_score=0, accepted=False)
            net_profit = strategy.current_balance - strategy.initial_balance
            net_loss = strategy.initial_balance - strategy.current_balance if strategy.current_balance < strategy.initial_balance else 0
            await display_account_stats(strategy)
            print("🔥 Waiting for a new signal 🔥")
            return

        start_prepare_time = time.time()
        prepared_symbol, duration, prepared_direction = await prepare_trade(
            client, symbol, trade_time, direction, strategy.settings, trade_time_exact=trade_time_exact, logger=logger
        )
        logging.info(f"Preparation time: {(time.time() - start_prepare_time):.3f} seconds")

        if prepared_symbol is None or duration is None or prepared_direction is None:
            logging.warning(f"فشل تحضير الصفقة لـ {symbol}")
            signal_id = logger.log_signal(symbol, trade_time, direction, signal_score=0, accepted=False)
            net_profit = strategy.current_balance - strategy.initial_balance
            net_loss = strategy.initial_balance - strategy.current_balance if strategy.current_balance < strategy.initial_balance else 0
            await display_account_stats(strategy)
            print("🔥 Waiting for a new signal 🔥")
            return

        # التحقق من وقت الصفقة
        if trade_time_exact:
            target_tz = pytz.timezone('America/Sao_Paulo')
            current_time = datetime.now(target_tz)
            try:
                trade_time_obj = datetime.strptime(trade_time_exact, "%H:%M:%S").replace(
                    year=current_time.year, month=current_time.month, day=current_time.day
                )
                trade_time_obj = target_tz.localize(trade_time_obj)
                if trade_time_obj < current_time:
                    trade_time_obj += timedelta(days=1)
                
                time_diff = (trade_time_obj - current_time).total_seconds()
                logging.info(f"فرق الوقت للصفقة: {time_diff} ثانية")
                if time_diff > 600:
                    logging.warning(f"وقت الصفقة بعيد: {trade_time_exact}, فرق الوقت: {time_diff} ثانية")
                    print(f"⚠️ وقت الصفقة بعيد: {trade_time_exact}")
                    signal_id = logger.log_signal(symbol, trade_time_exact, direction, signal_score=0, accepted=False)
                    await display_account_stats(strategy)
                    print("�fire: Waiting for a new signal 🔥")
                    return
                elif time_diff < -30:
                    logging.warning(f"وقت الصفقة قد مضى: {trade_time_exact}, فرق الوقت: {time_diff} ثانية")
                    print(f"⚠️ وقت الصفقة قد مضى: {trade_time_exact}")
                    signal_id = logger.log_signal(symbol, trade_time_exact, direction, signal_score=0, accepted=False)
                    await display_account_stats(strategy)
                    print("🔥 Waiting for a new signal 🔥")
                    return

                if time_diff > 0.5:  # عازل زمني 0.5 ثانية
                    start_wait_time = time.time()
                    print("ℹ️ Press 's' to skip this trade")
                    while time_diff > 0.5:
                        sys.stdout.write(f"\r⏱️ Waiting: {time_diff:.2f} | Press 's' to skip")
                        sys.stdout.flush()
                        if await asyncio.to_thread(check_for_skip, 0.01):
                            logging.info(f"تم تخطي الصفقة لـ {symbol} بواسطة المستخدم")
                            print(f"\n✅ Trade skipped by user for {symbol}")
                            signal_id = logger.log_signal(symbol, trade_time_exact, direction, signal_score=0, accepted=False)
                            await display_account_stats(strategy)
                            print("🔥 Waiting for a new signal 🔥")
                            return
                        await asyncio.sleep(0.001)  # تقليل النوم إلى 0.001 ثانية
                        time_diff = (trade_time_obj - datetime.now(target_tz)).total_seconds()

                    sys.stdout.write("\r" + " " * 50 + "\r")
                    sys.stdout.flush()
                    logging.info(f"Waiting time: {(time.time() - start_wait_time):.3f}")

            except ValueError:
                logging.error(f"تنسيق وقت الصفقة غير صحيح: {trade_time_exact}")
                print(f"❌ تنسيق وقت الصفقة غير صحيح: {trade_time_exact}")
                signal_id = logger.log_signal(symbol, trade_time_exact, direction, signal_score=0, accepted=False)
                await display_account_stats(strategy)
                print("🔥 Waiting for a new signal 🔥")
                return

        # تنفيذ الصفقة الأولى
        amount = float(strategy.get_amount())
        balance_before = await client.balance()
        logging.info(f"الرصيد قبل الصفقة: {balance_before:.2f}, المبلغ: {amount:.2f}")
        signal_id = logger.log_signal(symbol, trade_time, direction, signal_score=1, accepted=True)

        print("Started ...👍🏼")
        trade_id = await safe_execute_trade(client, prepared_symbol, amount, duration, prepared_direction, strategy.settings["payout"], strategy)
        execution_duration = time.time() - start_prepare_time
        logging.info(f"Execution time: {execution_duration:.3f} seconds")

        if trade_id is None:
            logging.error(f"فشل تنفيذ الصفقة لـ {prepared_symbol}")
            print(f"❌ فشل تنفيذ الصفقة لـ {prepared_symbol}")
            logger.log_trade(signal_id, symbol, prepared_direction, amount, "failed", balance_before, signal_score=0)
            await display_account_stats(strategy)
            print("🔥 Waiting for a new signal 🔥")
            return

        trade_data = await wait_for_result(client, trade_id, duration)
        result = trade_data.get('result') if trade_data else "loss"
        balance_after = await client.balance()
        strategy.update_balance(balance_after)
        profit_or_loss = float(trade_data.get('profit', -amount)) if trade_data else -amount

        if result == "win":
            result_display = f"WIN ✅{strategy.loss_count if strategy.loss_count > 0 else ''}"
            trade_profit = balance_after - balance_before if balance_after > balance_before else profit_or_loss
            trade_loss = 0.0
        elif result == "loss":
            result_display = f"Martingale {strategy.loss_count + 1}"
            trade_profit = 0.0
            trade_loss = balance_before - balance_after if balance_before > balance_after else amount
        elif result == "tie":
            result_display = "DOJI ⚖"
            trade_profit = 0.0
            trade_loss = 0.0
        else:
            result_display = result
            trade_profit = 0.0
            trade_loss = amount

        if result in ["win", "tie"]:
            os.system('cls' if os.name == 'nt' else 'clear')
        logging.info(f"تم تنفيذ الصفقة: {prepared_symbol} ({prepared_direction}), المبلغ: {amount:.2f}, النتيجة: {result_display}, الرصيد: {balance_after:.2f}")
        print(f"✅ The trade was a {result_display}")

        logging.info(f"ربح/خسارة الصفقة: {trade_profit:.2f}, الرصيد قبل: {balance_before:.2f}, الرصيد بعد: {balance_after:.2f}")
        logger.log_trade(signal_id, symbol, prepared_direction, amount, result, balance_after, signal_score=1)
        continue_trading = await strategy.update_amount(result, amount, profit_or_loss, payout)

        print(f"💰 Profit: {trade_profit:.2f}, Loss: {trade_loss:.2f}")
        if not continue_trading or not strategy.is_active:
            if result == "loss" and strategy.loss_count >= strategy.settings["max_loss_count"]:
                print(f"✖️ Loss")
            elif result == "win":
                print(f"WIN ✅")
            strategy.loss_count = 0  # إعادة تعيين loss_count بعد التوقف
            await display_account_stats(strategy)
            print("🔥 Waiting for a new signal 🔥")
            if not strategy.is_active:
                net_profit = strategy.current_balance - strategy.initial_balance
                net_loss = strategy.initial_balance - strategy.current_balance if strategy.current_balance < strategy.initial_balance else 0
                if net_profit >= strategy.settings["profit"]:
                    logging.info(f"توقف التداول بعد الوصول إلى الحد الأقصى للربح ({strategy.settings['profit']})")
                    print(f"🛑 توقف الروبوت: الوصول إلى الحد الأقصى للربح ({strategy.settings['profit']})")
                elif net_loss >= strategy.settings["loss"]:
                    logging.info(f"توقف التداول بعد الوصول إلى الحد الأقصى للخسارة ({strategy.settings['loss']})")
                    print(f"🛑 توقف الروبوت: الوصول إلى الحد الأقصى للخسارة ({strategy.settings['loss']})")
                await display_account_stats(strategy)
                print("👋 Session ended and logged.")
            return

        # حلقة المارتينجال
        while result == "loss" and strategy.is_active:
            amount = float(strategy.get_amount())
            balance_before = await client.balance()
            logging.info(f"الرصيد قبل الصفقة المضاعفة: {balance_before:.2f}, المبلغ: {amount:.2f}")
            signal_id = logger.log_signal(symbol, trade_time, direction, signal_score=1, accepted=True)

            print(f"Started Martingale {strategy.loss_count} ...👍🏼")
            trade_id = await safe_execute_trade(client, prepared_symbol, amount, duration, prepared_direction, strategy.settings["payout"], strategy)
            execution_duration = time.time() - start_prepare_time
            logging.info(f"Execution time: {execution_duration:.3f} seconds")

            if trade_id is None:
                logging.error(f"فشل تنفيذ الصفقة المضاعفة لـ {prepared_symbol}")
                print(f"❌ فشل تنفيذ الصفقة المضاعفة لـ {prepared_symbol}")
                logger.log_trade(signal_id, symbol, prepared_direction, amount, "failed", balance_before, signal_score=0)
                strategy.loss_count = 0  # إعادة تعيين عند الفشل
                await display_account_stats(strategy)
                print("🔥 Waiting for a new signal 🔥")
                return

            trade_data = await wait_for_result(client, trade_id, duration)
            result = trade_data.get('result') if trade_data else "loss"
            balance_after = await client.balance()
            strategy.update_balance(balance_after)
            profit_or_loss = float(trade_data.get('profit', -amount)) if trade_data else -amount

            if result == "win":
                result_display = f"WIN ✅{strategy.loss_count if strategy.loss_count > 0 else ''}"
                trade_profit = balance_after - balance_before if balance_after > balance_before else profit_or_loss
                trade_loss = 0.0
            elif result == "loss":
                result_display = f"Martingale {strategy.loss_count + 1}"
                trade_profit = 0.0
                trade_loss = balance_before - balance_after if balance_before > balance_after else amount
            elif result == "tie":
                result_display = "DOJI ⚖"
                trade_profit = 0.0
                trade_loss = 0.0
            else:
                result_display = result
                trade_profit = 0.0
                trade_loss = amount

            if result in ["win", "tie"]:
                os.system('cls' if os.name == 'nt' else 'clear')
            logging.info(f"تم تنفيذ الصفقة المضاعفة: {prepared_symbol} ({prepared_direction}), المبلغ: {amount:.2f}, النتيجة: {result_display}, الرصيد: {balance_after:.2f}")
            print(f"✅ The trade was a {result_display}")

            logging.info(f"ربح/خسارة الصفقة المضاعفة: {trade_profit:.2f}, الرصيد قبل: {balance_before:.2f}, الرصيد بعد: {balance_after:.2f}")
            logger.log_trade(signal_id, symbol, prepared_direction, amount, result, balance_after, signal_score=1)
            continue_trading = await strategy.update_amount(result, amount, profit_or_loss, payout)

            print(f"💰 Profit: {trade_profit:.2f}, Loss: {trade_loss:.2f}")
            if not continue_trading or not strategy.is_active:
                if result == "loss" and strategy.loss_count >= strategy.settings["max_loss_count"]:
                    print(f"✖️ Loss")
                elif result == "win":
                    print(f"WIN ✅")
                strategy.loss_count = 0  # إعادة تعيين loss_count بعد التوقف
                await display_account_stats(strategy)
                print("🔥 Waiting for a new signal 🔥")
                logging.info(f"توقف حلقة المارتينجال: continue_trading={continue_trading}, is_active={strategy.is_active}, loss_count={strategy.loss_count}")
                if not strategy.is_active:
                    net_profit = strategy.current_balance - strategy.initial_balance
                    net_loss = strategy.initial_balance - strategy.current_balance if strategy.current_balance < strategy.initial_balance else 0
                    if net_profit >= strategy.settings["profit"]:
                        logging.info(f"توقف التداول بعد الوصول إلى الحد الأقصى للربح ({strategy.settings['profit']})")
                        print(f"🛑 توقف الروبوت: الوصول إلى الحد الأقصى للربح ({strategy.settings['profit']})")
                    elif net_loss >= strategy.settings["loss"]:
                        logging.info(f"توقف التداول بعد الوصول إلى الحد الأقصى للخسارة ({strategy.settings['loss']})")
                        print(f"🛑 توقف الروبوت: الوصول إلى الحد الأقصى للخسارة ({strategy.settings['loss']})")
                    await display_account_stats(strategy)
                    print("👋 Session ended and logged.")
                return
    except Exception as e:
        logging.error(f"خطأ أثناء معالجة الإشارة: {str(e)}")
        print(f"⚠️ خطأ أثناء معالجة الإشارة: {str(e)}")
        try:
            symbol = message.get("symbol", "unknown")
            trade_time = message.get("duration", "unknown")
            direction = message.get("direction", "unknown")
            signal_id = logger.log_signal(symbol, trade_time, direction, signal_score=0, accepted=False)
        except Exception as log_error:
            logging.warning(f"⚠️ فشل تسجيل الإشارة أثناء الخطأ: {log_error}")
        await display_account_stats(strategy)
        print("🔥 Waiting for a new signal 🔥")
    finally:
        logging.info(f"Total signal handling time: {(time.time() - start_total_time):.3f} seconds")