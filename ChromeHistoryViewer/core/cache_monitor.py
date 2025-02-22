import os
import sqlite3
import requests
from typing import Dict, Set, Optional
from PySide6.QtCore import QThread, Signal
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

from ..config import (
    CHROME_DIR, CHROME_CACHE, CHROME_NETWORK,
    CHROME_COOKIES, DEFAULT_HEADERS
)

class CacheHandler(FileSystemEventHandler):
    """处理缓存文件变化的事件处理器"""
    def __init__(self, callback):
        self.callback = callback
        
    def on_created(self, event):
        if not event.is_directory:
            self.callback(event.src_path)
            
    def on_modified(self, event):
        if not event.is_directory:
            self.callback(event.src_path)

class ChromeCacheMonitor(QThread):
    """监控Chrome缓存的线程"""
    content_ready = Signal(str, str)  # URL, content
    
    def __init__(self):
        super().__init__()
        self.is_running = False
        self.observer = None
        self.url_patterns: Set[str] = set()
        
    def get_cookies(self, domain: str) -> Dict[str, str]:
        """获取指定域名的cookies"""
        cookies = {}
        temp_cookies = os.path.join(os.path.dirname(CHROME_COOKIES), 'temp_cookies')
        try:
            # 复制cookies文件
            from ..core.utils import copy_file_safe
            if not copy_file_safe(CHROME_COOKIES, temp_cookies):
                return cookies
            
            # 连接数据库
            conn = sqlite3.connect(temp_cookies)
            cursor = conn.cursor()
            
            # 查询cookies
            cursor.execute('''
                SELECT name, value, host_key
                FROM cookies
                WHERE host_key LIKE ?
            ''', ('%' + domain + '%',))
            
            for name, value, host in cursor.fetchall():
                cookies[name] = value
                
        except Exception as e:
            print(f"读取cookies时出错: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()
            if os.path.exists(temp_cookies):
                os.remove(temp_cookies)
        
        return cookies
        
    def fetch_with_cookies(self, url: str) -> Optional[str]:
        """使用cookies获取页面内容"""
        try:
            # 从URL中提取域名
            domain = url.split('/')[2]
            cookies = self.get_cookies(domain)
            
            response = requests.get(
                url,
                headers=DEFAULT_HEADERS,
                cookies=cookies,
                timeout=15
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            
            return response.text
            
        except Exception as e:
            print(f"使用cookies获取页面失败: {str(e)}")
            return None
    
    def process_cache_file(self, cache_file: str) -> None:
        """处理缓存文件"""
        try:
            if os.path.getsize(cache_file) < 100:  # 跳过太小的文件
                return
                
            with open(cache_file, 'rb') as f:
                content = f.read()
                
            # 尝试以不同编码解码内容
            for encoding in ['utf-8', 'latin1', 'gbk', 'gb2312']:
                try:
                    content_str = content.decode(encoding, errors='ignore')
                    
                    # 检查是否包含我们要找的URL
                    for url in self.url_patterns:
                        if url in content_str:
                            # 首先尝试从缓存提取HTML
                            html_start = content_str.find('<html')
                            html_end = content_str.rfind('</html>')
                            
                            if html_start >= 0 and html_end >= 0:
                                html_content = content_str[html_start:html_end + 7]
                                if len(html_content) > 1000:  # 确保内容足够长
                                    self.content_ready.emit(url, html_content)
                                    self.remove_url_from_watch(url)
                                    return
                            
                            # 如果从缓存无法获取完整HTML，尝试使用cookies重新获取
                            html_content = self.fetch_with_cookies(url)
                            if html_content and len(html_content) > 1000:
                                self.content_ready.emit(url, html_content)
                                self.remove_url_from_watch(url)
                            break
                except:
                    continue
                    
        except Exception as e:
            print(f"处理缓存文件时出错: {str(e)}")

    def add_url_to_watch(self, url: str) -> None:
        """添加要监视的URL"""
        self.url_patterns.add(url)
        
    def remove_url_from_watch(self, url: str) -> None:
        """移除监视的URL"""
        self.url_patterns.discard(url)
    
    def run(self) -> None:
        """运行缓存监控"""
        try:
            self.is_running = True
            
            # 创建文件系统观察者
            self.observer = Observer()
            handler = CacheHandler(self.process_cache_file)
            
            # 监控Cache目录
            if os.path.exists(CHROME_CACHE):
                self.observer.schedule(handler, CHROME_CACHE, recursive=False)
                
            # 监控Network目录
            if os.path.exists(CHROME_NETWORK):
                self.observer.schedule(handler, CHROME_NETWORK, recursive=True)
            
            self.observer.start()
            
            # 首次扫描现有缓存
            self.scan_existing_cache()
            
            # 保持线程运行，但每秒检查是否需要停止
            while self.is_running:
                self.msleep(1000)  # 使用QThread的msleep而不是time.sleep
                
        except Exception as e:
            print(f"缓存监控线程出错: {str(e)}")
        finally:
            if self.observer:
                self.observer.stop()
                self.observer.join()
            self.is_running = False
    
    def scan_existing_cache(self) -> None:
        """扫描现有的缓存文件"""
        for directory in [CHROME_CACHE, CHROME_NETWORK]:
            if not os.path.exists(directory):
                continue
                
            for root, _, files in os.walk(directory):
                for file in files:
                    if not self.is_running:
                        return
                    self.process_cache_file(os.path.join(root, file))
        
    def stop(self) -> None:
        """停止监控"""
        self.is_running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        self.wait(1000)  # 最多等待1秒
        if self.isRunning():
            self.terminate()  # 强制终止
            self.wait() 