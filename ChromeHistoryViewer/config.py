import os
from pathlib import Path

# Chrome相关路径
CHROME_DIR = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default')
CHROME_HISTORY = os.path.join(CHROME_DIR, 'History')
# 更新缓存目录路径
CHROME_CACHE_DIR = os.path.expanduser('~/Library/Caches/Google/Chrome')
CHROME_CACHE = os.path.join(CHROME_CACHE_DIR, 'Default/Cache')
CHROME_CODE_CACHE = os.path.join(CHROME_CACHE_DIR, 'Default/Code Cache')
CHROME_NETWORK = os.path.join(CHROME_CACHE_DIR, 'Default/Cache/Cache_Data')
CHROME_COOKIES = os.path.join(CHROME_DIR, 'Cookies')

# 应用程序相关路径
APP_DIR = os.path.expanduser('~/Library/Application Support/ChromeHistoryViewer')
TEMP_DIR = os.path.join(APP_DIR, 'temp')
DEFAULT_SAVE_DIR = os.path.join(Path.home(), 'Downloads/markdown_exports')

# 创建必要的目录
os.makedirs(APP_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DEFAULT_SAVE_DIR, exist_ok=True)

# UI配置
WINDOW_SIZE_RATIO = 0.8  # 窗口大小占屏幕的比例
DEFAULT_NUM_RECORDS = 100  # 默认显示的历史记录数量
DEFAULT_CHECK_INTERVAL = 5  # 默认监控间隔（秒）
BATCH_SIZE = 20  # 每批处理的URL数量

# 请求头
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
}

# RAGFlow配置
RAGFLOW_API_URL = os.getenv('RAGFLOW_API_URL', 'http://localhost:8000')  # RAGFlow API地址
RAGFLOW_API_KEY = os.getenv('RAGFLOW_API_KEY', '')  # RAGFlow API密钥
RAGFLOW_ENABLED = bool(RAGFLOW_API_KEY)  # 是否启用RAGFlow集成 