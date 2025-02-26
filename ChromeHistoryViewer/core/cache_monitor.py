import os
import sqlite3
import requests
from typing import Dict, Set, Optional
from PySide6.QtCore import QThread, Signal, QTimer
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
        
        # 检查缓存目录是否存在
        if not os.path.exists(CHROME_CACHE):
            print(f"警告: Chrome缓存目录不存在: {CHROME_CACHE}")
        if not os.path.exists(CHROME_NETWORK):
            print(f"警告: Chrome网络缓存目录不存在: {CHROME_NETWORK}")
        
    def get_cookies(self, domain: str) -> Dict[str, str]:
        """获取指定域名的cookies"""
        cookies = {}
        temp_cookies = os.path.join(os.path.dirname(CHROME_COOKIES), 'temp_cookies')
        try:
            # 复制cookies文件
            from ..core.utils import copy_file_safe
            if not copy_file_safe(CHROME_COOKIES, temp_cookies):
                print(f"无法复制Cookie文件: {CHROME_COOKIES}")
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
                
            print(f"获取到 {len(cookies)} 个cookies，域名: {domain}")
                
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
        max_retries = 2
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # 从URL中提取域名
                domain = url.split('/')[2]
                cookies = self.get_cookies(domain)
                
                print(f"尝试使用cookies获取页面: {url} (第{retry_count+1}次尝试)")
                print(f"使用的cookies: {cookies if cookies else '无'}")
                
                headers = DEFAULT_HEADERS.copy()  # 复制一份，避免修改原始对象
                
                # 增加一些额外的headers，使请求更像浏览器
                headers['Referer'] = f"https://{domain}/"
                headers['Sec-Fetch-Dest'] = 'document'
                headers['Sec-Fetch-Mode'] = 'navigate'
                headers['Sec-Fetch-Site'] = 'same-origin'
                
                response = requests.get(
                    url,
                    headers=headers,
                    cookies=cookies,
                    timeout=15,
                    allow_redirects=True  # 允许重定向
                )
                
                if response.status_code != 200:
                    print(f"请求返回非200状态码: {response.status_code}")
                    if retry_count < max_retries:
                        retry_count += 1
                        print(f"将在1秒后重试...")
                        time.sleep(1)
                        continue
                
                # 尝试确定正确的编码
                response.encoding = response.apparent_encoding or 'utf-8'
                
                content_length = len(response.text)
                print(f"成功获取页面内容，长度: {content_length}")
                
                # 检查内容是否包含HTML结构
                if '<html' in response.text or '<!DOCTYPE html' in response.text:
                    print(f"内容包含HTML结构")
                    return response.text
                else:
                    print(f"内容不包含HTML结构，可能不是HTML页面")
                    if content_length > 5000:  # 如果内容较长，可能仍然有用
                        print(f"内容较长，尝试使用")
                        return response.text
                    elif retry_count < max_retries:
                        retry_count += 1
                        print(f"将在1秒后重试...")
                        time.sleep(1)
                        continue
                    return response.text
                
            except Exception as e:
                print(f"使用cookies获取页面失败: {str(e)}")
                if retry_count < max_retries:
                    retry_count += 1
                    print(f"将在1秒后重试...")
                    time.sleep(1)
                else:
                    return None
        
        return None
    
    def process_cache_file(self, cache_file: str) -> None:
        """处理缓存文件"""
        try:
            if not os.path.exists(cache_file):
                return
                
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
                            print(f"在缓存文件中找到URL: {url}")
                            print(f"缓存文件路径: {cache_file}")
                            print(f"缓存文件大小: {os.path.getsize(cache_file)} 字节")
                            
                            # 首先尝试从缓存提取HTML
                            html_start = content_str.find('<html')
                            if html_start < 0:
                                html_start = content_str.find('<!DOCTYPE html')
                            html_end = content_str.rfind('</html>')
                            
                            # 如果找到完整的HTML标签
                            if html_start >= 0 and html_end >= 0 and html_end > html_start:
                                html_content = content_str[html_start:html_end + 7]
                                if len(html_content) > 1000:  # 确保内容足够长
                                    print(f"从缓存提取到HTML内容，长度: {len(html_content)}")
                                    self.content_ready.emit(url, html_content)
                                    self.remove_url_from_watch(url)
                                    return
                                else:
                                    print(f"提取的HTML内容太短: {len(html_content)}")
                            
                            # 尝试查找更松散的HTML标记
                            body_start = content_str.find('<body')
                            body_end = content_str.rfind('</body>')
                            
                            if body_start >= 0 and body_end >= 0 and body_end > body_start:
                                body_content = content_str[body_start:body_end + 7]
                                if len(body_content) > 1000:
                                    print(f"从缓存提取到BODY内容，长度: {len(body_content)}")
                                    # 构造完整的HTML
                                    html_content = f"<html><head><title>{url}</title></head>{body_content}</html>"
                                    self.content_ready.emit(url, html_content)
                                    self.remove_url_from_watch(url)
                                    return
                                else:
                                    print(f"提取的BODY内容太短: {len(body_content)}")
                            
                            # 如果找到了一些HTML结构但不完整
                            if (html_start >= 0 or body_start >= 0) and len(content_str) > 5000:
                                print(f"找到部分HTML结构，尝试使用整个内容，长度: {len(content_str)}")
                                self.content_ready.emit(url, content_str)
                                self.remove_url_from_watch(url)
                                return
                                
                            # 打印缓存文件的前200个字符，帮助调试
                            print(f"缓存文件内容前200个字符: {content_str[:200]}")
                            
                            # 如果从缓存无法获取完整HTML，尝试使用cookies重新获取
                            print(f"尝试直接获取URL内容: {url}")
                            html_content = self.fetch_with_cookies(url)
                            if html_content and len(html_content) > 1000:
                                print(f"成功直接获取URL内容，长度: {len(html_content)}")
                                self.content_ready.emit(url, html_content)
                                self.remove_url_from_watch(url)
                            else:
                                print(f"直接获取URL内容失败或内容太短")
                            break
                except Exception as e:
                    print(f"使用编码 {encoding} 解析缓存文件时出错: {str(e)}")
                    continue
                    
        except Exception as e:
            print(f"处理缓存文件时出错: {str(e)}")

    def add_url_to_watch(self, url: str) -> None:
        """添加要监视的URL"""
        print(f"添加URL到监视列表: {url}")
        self.url_patterns.add(url)
        
        # 每添加一个URL，就扫描一次现有缓存
        # 为避免频繁扫描，可以使用一个计数器或定时器来控制扫描频率
        # 这里简单起见，直接调用scan_existing_cache方法
        QTimer.singleShot(0, self.scan_existing_cache)
    
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
                print(f"开始监控Chrome缓存目录: {CHROME_CACHE}")
                self.observer.schedule(handler, CHROME_CACHE, recursive=False)
                
            # 监控Network目录
            if os.path.exists(CHROME_NETWORK):
                print(f"开始监控Chrome网络缓存目录: {CHROME_NETWORK}")
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
        print("开始扫描现有缓存文件...")
        
        # 如果没有URL需要监视，直接返回
        if not self.url_patterns:
            print("没有需要监视的URL，跳过缓存扫描")
            return
            
        print(f"需要监视的URL: {self.url_patterns}")
        cache_files_count = 0
        
        for directory in [CHROME_CACHE, CHROME_NETWORK]:
            if not os.path.exists(directory):
                print(f"缓存目录不存在: {directory}")
                continue
                
            print(f"扫描缓存目录: {directory}")
            for root, _, files in os.walk(directory):
                for file in files:
                    if not self.is_running:
                        return
                    cache_files_count += 1
                    if cache_files_count % 100 == 0:
                        print(f"已扫描 {cache_files_count} 个缓存文件...")
                    self.process_cache_file(os.path.join(root, file))
                    
        print(f"缓存扫描完成，共扫描 {cache_files_count} 个文件")
        
        # 如果还有未处理的URL，尝试直接获取
        if self.url_patterns:
            print(f"缓存扫描后仍有 {len(self.url_patterns)} 个未处理的URL")
            print(f"尝试直接获取这些URL的内容...")
            urls_to_fetch = list(self.url_patterns)  # 创建副本，因为在循环中会修改self.url_patterns
            
            for url in urls_to_fetch:
                if not self.is_running:
                    return
                    
                print(f"直接获取URL: {url}")
                html_content = self.fetch_with_cookies(url)
                
                if html_content:
                    content_length = len(html_content)
                    print(f"成功获取URL内容，长度: {content_length}")
                    
                    if content_length > 1000:
                        self.content_ready.emit(url, html_content)
                        self.remove_url_from_watch(url)
                        print(f"成功处理URL: {url}")
                    else:
                        print(f"获取的内容太短，不处理: {url}")
                else:
                    print(f"无法获取URL内容: {url}")
        
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