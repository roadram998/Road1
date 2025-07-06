import redis
import json
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('errors.log', mode='a', encoding='utf-8')]
)

class RedisClient:
    def __init__(self, host='localhost', port=6379, db=0):
        try:
            self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self.client.ping()
            logging.info("Connected to Redis successfully")
            self.local_cache = {}  # تحسين: إضافة قاموس للتخزين المؤقت المحلي
            self.cache_timestamps = {}  # تحسين: تتبع أوقات التخزين المؤقت
        except redis.ConnectionError as e:
            logging.error(f"Failed to connect to Redis: {str(e)}")
            raise

    def set_data(self, key: str, value: dict, ttl: int = 180):  # تحسين: تغيير TTL إلى 3 دقائق (180 ثانية)
        """Store data in Redis with TTL and update local cache."""
        try:
            self.local_cache[key] = value  # تحسين: تخزين في الذاكرة المحلية
            self.cache_timestamps[key] = time.time()  # تحسين: تسجيل وقت التخزين
            self.client.setex(key, ttl, json.dumps(value))
            logging.info(f"Stored data in Redis for key: {key}")
        except Exception as e:
            logging.error(f"Failed to set data in Redis for key {key}: {str(e)}")

    def get_data(self, key: str) -> dict:
        """Retrieve data from local cache or Redis."""
        try:
            # تحسين: التحقق من التخزين المؤقت المحلي أولاً
            if key in self.local_cache and (time.time() - self.cache_timestamps.get(key, 0)) < 180:
                logging.info(f"Retrieved data from local cache for key: {key}")
                return self.local_cache[key]
            
            data = self.client.get(key)
            if data:
                value = json.loads(data)
                self.local_cache[key] = value  # تحسين: تحديث التخزين المؤقت المحلي
                self.cache_timestamps[key] = time.time()
                logging.info(f"Retrieved data from Redis for key: {key}")
                return value
            return None
        except Exception as e:
            logging.error(f"Failed to get data from Redis for key {key}: {str(e)}")
            return None

redis_client = RedisClient()