import sys
import os
import sqlite3
import shutil
import requests
import html2text
import hashlib
import argparse
import unicodedata
import re
import json
import threading
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QTableWidget, 
                           QTableWidgetItem, QVBoxLayout, QWidget,
                           QMessageBox, QPushButton, QLabel, QProgressBar,
                           QHBoxLayout, QSpinBox, QCheckBox)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRect
from PySide6.QtGui import QDesktopServices, QScreen
from PySide6.QtCore import QUrl
from dateutil.parser import parse
import base64
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import signal

def clean_filename(title):
    """Clean filename to be safe for all operating systems while preserving unicode characters"""
    # 移除不可见字符
    title = "".join(char for char in title if not unicodedata.category(char).startswith('C'))
    
    # 替换Windows/Unix文件系统中的非法字符
    illegal_chars = r'[<>:"/\\|?*]'
    title = re.sub(illegal_chars, '_', title)
    
    # 确保文件名不以点或空格开始或结束
    title = title.strip('. ')
    
    # 如果标题为空，返回None
    if not title or title.isspace():
        return None
        
    # 限制长度，但要确保不会在多字节字符中间截断
    if len(title) > 50:
        title = title[:50].rsplit(' ', 1)[0]
    
    return title

def read_chrome_session():
    """读取Chrome的Session Storage"""
    session_path = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/Sessions')
    local_storage_path = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/Local Storage/leveldb')
    current_tabs = {}
    
    if not os.path.exists(session_path):
        return current_tabs
        
    try:
        # 创建临时目录
        temp_dir = os.path.expanduser('~/Library/Application Support/ChromeHistoryViewer/temp_session')
        os.makedirs(temp_dir, exist_ok=True)
        
        # 复制最新的会话文件
        latest_session = None
        latest_time = 0
        
        for file in os.listdir(session_path):
            if file.startswith('Session_') or file == 'Current Session':
                file_path = os.path.join(session_path, file)
                file_time = os.path.getmtime(file_path)
                if file_time > latest_time:
                    latest_time = file_time
                    latest_session = file_path
        
        if latest_session:
            temp_session = os.path.join(temp_dir, 'temp_session')
            shutil.copy2(latest_session, temp_session)
            
            # 读取会话文件
            with open(temp_session, 'rb') as f:
                data = f.read()
            
            # 尝试读取Local Storage
            try:
                if os.path.exists(local_storage_path):
                    # 复制Local Storage文件到临时目录
                    temp_storage = os.path.join(temp_dir, 'temp_storage')
                    for file in os.listdir(local_storage_path):
                        if file.endswith('.log'):
                            shutil.copy2(os.path.join(local_storage_path, file), 
                                       os.path.join(temp_dir, file))
                    
                    import leveldb
                    db = leveldb.LevelDB(temp_dir)
                    
                    # 遍历所有键值对
                    for key, value in db.RangeIter():
                        try:
                            key_str = key.decode('utf-8', errors='ignore')
                            if '_https://' in key_str:
                                url = key_str.split('_https://')[-1]
                                url = 'https://' + url
                                try:
                                    content = value.decode('utf-8', errors='ignore')
                                    if url not in current_tabs:
                                        current_tabs[url] = {'content': content}
                                except:
                                    pass
                        except:
                            continue
            except Exception as e:
                print(f"读取Local Storage时出错: {str(e)}")
                
            # 查找URL和标题
            i = 0
            while i < len(data):
                try:
                    # 查找URL标记
                    url_start = data.find(b'http', i)
                    if url_start == -1:
                        break
                    
                    # 查找URL结束位置
                    url_end = data.find(b'\x00', url_start)
                    if url_end == -1:
                        break
                    
                    url = data[url_start:url_end].decode('utf-8')
                    
                    # 在URL之后查找可能的标题和内容
                    title_start = url_end + 1
                    title_end = data.find(b'\x00', title_start)
                    if title_end - title_start > 1:
                        try:
                            title = data[title_start:title_end].decode('utf-8')
                            if len(title) > 1 and not title.startswith(('http://', 'https://')):
                                # 查找可能的页面内容
                                content_start = title_end + 1
                                content_end = data.find(b'\x00\x00\x00\x00', content_start)
                                if content_end > content_start:
                                    try:
                                        content = data[content_start:content_end].decode('utf-8', errors='ignore')
                                        if len(content) > 100:  # 确保内容有效
                                            if url not in current_tabs:
                                                current_tabs[url] = {}
                                            current_tabs[url]['title'] = title
                                            current_tabs[url]['content'] = content
                                    except:
                                        pass
                        except UnicodeDecodeError:
                            pass
                    
                    i = title_end + 1
                except Exception as e:
                    print(f"解析会话数据时出错: {str(e)}")
                    i += 1
            
            # 清理临时文件
            os.remove(temp_session)
            
    except Exception as e:
        print(f"读取Chrome会话时出错: {str(e)}")
    finally:
        # 清理临时目录
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    return current_tabs

class ChromeCacheMonitor(QThread):
    content_ready = Signal(str, str)  # URL, content
    
    def __init__(self):
        super().__init__()
        self.is_running = False
        self.chrome_dir = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default')
        self.cache_dir = os.path.join(self.chrome_dir, 'Cache')
        self.network_dir = os.path.join(self.chrome_dir, 'Network')
        self.cookies_file = os.path.join(self.chrome_dir, 'Cookies')
        self.observer = None
        self.url_patterns = set()
        
    def get_cookies(self, domain):
        """获取指定域名的cookies"""
        cookies = {}
        temp_cookies = os.path.join(os.path.dirname(self.cookies_file), 'temp_cookies')
        try:
            # 复制cookies文件
            shutil.copy2(self.cookies_file, temp_cookies)
            
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
        
    def fetch_with_cookies(self, url):
        """使用cookies获取页面内容"""
        try:
            # 从URL中提取域名
            domain = url.split('/')[2]
            cookies = self.get_cookies(domain)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
            }
            
            response = requests.get(url, headers=headers, cookies=cookies, timeout=15)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            
            return response.text
            
        except Exception as e:
            print(f"使用cookies获取页面失败: {str(e)}")
            return None
    
    def process_cache_file(self, cache_file):
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

    def add_url_to_watch(self, url):
        """添加要监视的URL"""
        self.url_patterns.add(url)
        
    def remove_url_from_watch(self, url):
        """移除监视的URL"""
        self.url_patterns.discard(url)
        
    class CacheHandler(FileSystemEventHandler):
        def __init__(self, callback):
            self.callback = callback
            
        def on_created(self, event):
            if not event.is_directory:
                self.callback(event.src_path)
                
        def on_modified(self, event):
            if not event.is_directory:
                self.callback(event.src_path)
    
    def run(self):
        """运行缓存监控"""
        self.is_running = True
        
        # 创建文件系统观察者
        self.observer = Observer()
        handler = self.CacheHandler(self.process_cache_file)
        
        # 监控Cache目录
        if os.path.exists(self.cache_dir):
            self.observer.schedule(handler, self.cache_dir, recursive=False)
            
        # 监控Network目录
        if os.path.exists(self.network_dir):
            self.observer.schedule(handler, self.network_dir, recursive=True)
        
        self.observer.start()
        
        # 首次扫描现有缓存
        self.scan_existing_cache()
        
        # 保持线程运行
        while self.is_running:
            time.sleep(1)
            
    def scan_existing_cache(self):
        """扫描现有的缓存文件"""
        for directory in [self.cache_dir, self.network_dir]:
            if not os.path.exists(directory):
                continue
                
            for root, _, files in os.walk(directory):
                for file in files:
                    if not self.is_running:
                        return
                    self.process_cache_file(os.path.join(root, file))
        
    def stop(self):
        """停止监控"""
        self.is_running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
            
class WebPageDownloader(QThread):
    progress = Signal(int, str)
    page_finished = Signal(int, bool, str)
    finished = Signal(bool)
    
    def __init__(self, urls, save_dir, cache_monitor=None):
        super().__init__()
        self.urls = urls
        self.save_dir = save_dir
        self.converter = html2text.HTML2Text()
        self.converter.ignore_links = False
        self.converter.ignore_images = False
        self.converter.ignore_tables = False
        self.is_running = False
        self.cache_monitor = cache_monitor
        self.pending_urls = {}  # row -> (title, url)
        self.batch_size = 20  # 增加批处理大小
        
    def run(self):
        self.is_running = True
        total = len(self.urls)
        completed = 0
        
        # 先扫描一遍缓存目录
        if self.cache_monitor:
            self.cache_monitor.scan_existing_cache()
        
        # 按批次处理URL
        for i in range(0, len(self.urls), self.batch_size):
            if not self.is_running:
                self.finished.emit(False)
                return
                
            batch = self.urls[i:i + self.batch_size]
            
            # 添加到待处理列表
            for row, title, url in batch:
                self.pending_urls[row] = (title, url)
                if self.cache_monitor:
                    self.cache_monitor.add_url_to_watch(url)
            
            # 等待缓存内容（最多1秒）
            self.msleep(1000)
            
            # 处理这一批的URL
            for row, title, url in batch:
                if not self.is_running:
                    self.finished.emit(False)
                    return
                    
                try:
                    # 使用改进的文件名清理函数
                    safe_title = clean_filename(title)
                    if not safe_title:
                        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                        safe_title = f"untitled_{url_hash}"
                    
                    file_path = os.path.join(self.save_dir, f"{safe_title}.md")
                    
                    # 如果文件已存在，跳过
                    if os.path.exists(file_path):
                        self.page_finished.emit(row, True, "已存在")
                        completed += 1
                        continue
                    
                    # 如果还在待处理列表中，说明没有从缓存获取到内容
                    if row in self.pending_urls:
                        self.page_finished.emit(row, False, "未缓存")
                        completed += 1
                            
                except Exception as e:
                    self.page_finished.emit(row, False, str(e))
                    completed += 1
                
                # 每处理5个URL更新一次进度
                if completed % 5 == 0:
                    self.progress.emit(int(completed * 100 / total), f"已完成: {completed}/{total}")
            
            # 清理本批次的待处理URL
            for row, _, _ in batch:
                if row in self.pending_urls:
                    del self.pending_urls[row]
            
            # 更新总进度
            self.progress.emit(int(completed * 100 / total), f"已完成: {completed}/{total}")
        
        self.is_running = False
        self.finished.emit(True)

    def save_as_markdown(self, row, title, url, html_content, source):
        """保存为Markdown文件"""
        try:
            safe_title = clean_filename(title)
            if not safe_title:
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                safe_title = f"untitled_{url_hash}"
            
            file_path = os.path.join(self.save_dir, f"{safe_title}.md")
            
            # 配置HTML2Text
            self.converter.unicode_snob = True
            self.converter.body_width = 0
            self.converter.ignore_images = False
            self.converter.ignore_emphasis = False
            self.converter.ignore_links = False
            self.converter.protect_links = True
            self.converter.mark_code = True
            
            # 转换为Markdown
            markdown_content = f"# {title}\n\nURL: {url}\n来源: {source}\n\n---\n\n"
            markdown_content += self.converter.handle(html_content)
            
            # 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            self.page_finished.emit(row, True, f"完成({source})")
            
        except Exception as e:
            raise Exception(f"保存Markdown失败: {str(e)}")

    def stop(self):
        """停止下载进程"""
        self.is_running = False
        self.wait()  # 等待线程结束

    def handle_cache_content(self, url, content):
        """处理从缓存获取的内容"""
        print(f"下载器收到缓存内容: {url[:50]}...")
        if self.is_running:
            self.save_as_markdown(0, '', url, content, '缓存')

class HistoryMonitor(QThread):
    """监控Chrome历史记录更新的线程"""
    new_records = Signal(list)  # 发送新记录的信号
    
    def __init__(self, check_interval=5):
        super().__init__()
        self.check_interval = check_interval  # 检查间隔（秒）
        self.last_check_time = None
        self.is_running = False
        self.processed_urls = set()  # 记录已处理的URL
        
    def get_new_records(self):
        """获取新的历史记录"""
        history_path = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/History')
        
        # 创建临时目录
        temp_dir = os.path.expanduser('~/Library/Application Support/ChromeHistoryViewer')
        os.makedirs(temp_dir, exist_ok=True)
        temp_history = os.path.join(temp_dir, 'temp_history_monitor')
        
        try:
            # 复制历史记录文件
            shutil.copy2(history_path, temp_history)
            
            # 连接数据库
            conn = sqlite3.connect(temp_history)
            cursor = conn.cursor()
            
            # 获取上次检查时间之后的新记录
            if self.last_check_time is None:
                # 首次运行，获取最近的时间作为起点
                cursor.execute('SELECT MAX(last_visit_time) FROM urls')
                max_time = cursor.fetchone()[0]
                if max_time:
                    self.last_check_time = max_time - 1  # 减1以确保不会漏掉记录
                return []
            
            # 查询新记录，排除已处理的URL
            cursor.execute('''
                SELECT title, url, last_visit_time, visit_count 
                FROM urls 
                WHERE last_visit_time > ?
                ORDER BY last_visit_time DESC
            ''', (self.last_check_time,))
            
            new_records = []
            for record in cursor.fetchall():
                if record[1] not in self.processed_urls:  # 检查URL是否已处理
                    new_records.append(record)
                    self.processed_urls.add(record[1])
            
            # 更新最后检查时间
            if new_records:
                self.last_check_time = max(record[2] for record in new_records)
            
            return new_records
            
        except Exception as e:
            print(f"监控历史记录时出错: {str(e)}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()
            if os.path.exists(temp_history):
                os.remove(temp_history)

    def run(self):
        """运行监控线程"""
        self.is_running = True
        while self.is_running:
            try:
                new_records = self.get_new_records()
                if new_records:
                    self.new_records.emit(new_records)
            except Exception as e:
                print(f"监控线程错误: {str(e)}")
            
            # 等待下次检查
            for _ in range(self.check_interval):
                if not self.is_running:
                    break
                self.msleep(1000)  # 每秒检查一次是否需要停止
    
    def stop(self):
        """停止监控线程"""
        self.is_running = False
        self.wait()

class ChromeHistoryViewer(QMainWindow):
    def __init__(self, num_records=100):
        super().__init__()
        
        # 设置信号处理
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        self.setWindowTitle("Chrome History Viewer")
        
        # 获取主屏幕
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        # 计算窗口大小（屏幕的80%）
        window_width = int(screen_geometry.width() * 0.8)
        window_height = int(screen_geometry.height() * 0.8)
        
        # 计算窗口位置（居中）
        x = (screen_geometry.width() - window_width) // 2
        y = (screen_geometry.height() - window_height) // 2
        
        # 设置窗口大小和位置
        self.setGeometry(x, y, window_width, window_height)
        
        # 设置窗口属性
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        self.num_records = num_records
        
        # 设置保存目录
        current_dir = Path(__file__).parent.parent
        self.save_dir = os.path.join(current_dir, 'markdown_files')
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        
        # 初始化下载器为None
        self.downloader = None
        self.monitor = None
        
        # 加载已处理的URL集合
        self.processed_urls = self.load_processed_urls()
        
        # 初始化缓存监控器
        self.cache_monitor = ChromeCacheMonitor()
        self.cache_monitor.content_ready.connect(self.handle_cache_content)
        self.cache_monitor.start()
        
        # 初始化线程状态标志
        self._shutting_down = False
        
        self.initUI()
        
    def signal_handler(self, signum, frame):
        """处理终止信号"""
        print(f"收到信号: {signum}")
        self.force_cleanup()
        sys.exit(0)
        
    def force_cleanup(self):
        """强制清理所有资源"""
        try:
            # 停止所有线程
            if hasattr(self, 'downloader') and self.downloader:
                self.downloader.is_running = False
                self.downloader.terminate()
            
            if hasattr(self, 'monitor') and self.monitor:
                self.monitor.is_running = False
                self.monitor.terminate()
            
            if hasattr(self, 'cache_monitor') and self.cache_monitor:
                self.cache_monitor.is_running = False
                self.cache_monitor.terminate()
            
            # 关闭所有Chrome实例
            if sys.platform == 'darwin':  # macOS
                os.system('pkill "Google Chrome"')
            
        except Exception as e:
            print(f"强制清理时出错: {str(e)}")
            
    def closeEvent(self, event):
        """重写关闭事件，确保清理所有线程"""
        self._shutting_down = True
        
        try:
            self.force_cleanup()
            # 等待最多3秒
            for _ in range(3):
                QApplication.processEvents()
                time.sleep(0.1)
        except Exception as e:
            print(f"关闭时出错: {str(e)}")
        finally:
            event.accept()
        
    def initUI(self):
        """初始化UI"""
        # 创建主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 创建布局
        layout = QVBoxLayout()
        main_widget.setLayout(layout)
        
        # 创建顶部布局
        top_layout = QHBoxLayout()
        
        # 添加记录数量选择器
        self.records_spinbox = QSpinBox()
        self.records_spinbox.setRange(1, 1000)
        self.records_spinbox.setValue(self.num_records)
        self.records_spinbox.setSuffix(" 条记录")
        self.records_spinbox.valueChanged.connect(self.load_history)
        top_layout.addWidget(QLabel("显示最近"))
        top_layout.addWidget(self.records_spinbox)
        
        # 添加总体进度标签
        self.progress_label = QLabel("准备开始...")
        top_layout.addWidget(self.progress_label)
        top_layout.addStretch()
        
        layout.addLayout(top_layout)
        
        # 添加保存目录信息和打开按钮
        dir_layout = QHBoxLayout()
        dir_label = QLabel(f"保存目录: {self.save_dir}")
        dir_layout.addWidget(dir_label)
        
        open_dir_button = QPushButton("打开目录")
        open_dir_button.clicked.connect(self.open_save_dir)
        dir_layout.addWidget(open_dir_button)
        
        self.stop_button = QPushButton("停止转换")
        self.stop_button.clicked.connect(self.stop_conversion)
        self.stop_button.setEnabled(False)  # 初始状态禁用
        dir_layout.addWidget(self.stop_button)
        
        dir_layout.addStretch()
        
        layout.addLayout(dir_layout)
        
        # 添加总体进度条
        self.total_progress_bar = QProgressBar()
        layout.addWidget(self.total_progress_bar)
        
        # 添加自动监控选项
        monitor_layout = QHBoxLayout()
        self.monitor_checkbox = QCheckBox("自动监控新记录")
        self.monitor_checkbox.setChecked(False)
        self.monitor_checkbox.stateChanged.connect(self.toggle_monitor)
        monitor_layout.addWidget(self.monitor_checkbox)
        
        # 添加监控间隔选择器
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 60)
        self.interval_spinbox.setValue(5)
        self.interval_spinbox.setSuffix(" 秒")
        monitor_layout.addWidget(QLabel("检查间隔:"))
        monitor_layout.addWidget(self.interval_spinbox)
        monitor_layout.addStretch()
        
        # 将监控控件添加到布局中
        layout.insertLayout(1, monitor_layout)
        
        # 创建表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['状态', 'Title', 'URL', 'Visit Time', 'Visit Count'])
        layout.addWidget(self.table)
        
        # 加载历史记录
        self.load_history()
        
    def stop_conversion(self):
        """停止转换进程"""
        try:
            if self.downloader and self.downloader.is_running:
                self.stop_button.setEnabled(False)
                self.progress_label.setText("正在停止转换...")
                self.downloader.is_running = False
                self.downloader.wait()
                self.downloader = None
                
                # 强制刷新UI
                self.repaint()
        except Exception as e:
            print(f"Error in stop_conversion: {str(e)}")
    
    def start_conversion(self):
        """开始转换过程"""
        if self.downloader:
            QMessageBox.warning(self, "警告", "已有转换任务正在进行")
            return
        
        # 获取选中的行
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选择要转换的记录")
            return
        
        # 收集URL信息
        urls = []
        for row in sorted(selected_rows):
            title = self.table.item(row, 1).text()
            url = self.table.item(row, 3).text()
            urls.append((row, title, url))
        
        # 确保保存目录存在
        save_dir = self.save_dir
        os.makedirs(save_dir, exist_ok=True)
        
        # 初始化缓存监控
        self.cache_monitor = ChromeCacheMonitor()
        self.cache_monitor.content_ready.connect(self.handle_cache_content)
        self.cache_monitor.start()
        
        # 等待缓存监控启动
        time.sleep(1)
        
        # 初始化下载器
        self.downloader = WebPageDownloader(urls, save_dir, self.cache_monitor)
        self.downloader.progress.connect(self.update_total_progress)
        self.downloader.page_finished.connect(self.update_page_status)
        self.downloader.finished.connect(self.conversion_finished)
        
        # 更新UI状态
        self.stop_button.setEnabled(True)
        self.total_progress_bar.setValue(0)
        self.total_progress_bar.setVisible(True)
        self.progress_label.setText("正在转换...")
        
        # 启动下载线程
        self.downloader.start()

    def conversion_finished(self, normal_completion):
        """转换完成的处理"""
        try:
            if self.downloader:
                if normal_completion:
                    self.progress_label.setText("所有页面处理完成！")
                    # 确保UI更新后再显示对话框
                    QApplication.processEvents()
                    QMessageBox.information(self, "完成", "所有页面都已处理完成！")
                else:
                    self.progress_label.setText("转换已中断")
                
                self.stop_button.setEnabled(False)  # 禁用停止按钮
                self.downloader = None
                
                # 强制刷新UI
                self.repaint()
                QApplication.processEvents()
        except Exception as e:
            print(f"Error in conversion_finished: {str(e)}")

    def open_save_dir(self):
        """打开保存目录"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.save_dir))

    def update_page_status(self, row, success, message):
        """更新单个页面的状态"""
        try:
            status_item = QTableWidgetItem(message)
            if success:
                status_item.setBackground(Qt.green)
            else:
                status_item.setBackground(Qt.red)
            self.table.setItem(row, 0, status_item)
            
            # 减少UI更新频率
            if row % 5 == 0:
                self.table.viewport().update()
                QApplication.processEvents()
                
        except Exception as e:
            print(f"Error in update_page_status: {str(e)}")
    
    def update_total_progress(self, value, status):
        """更新总体进度"""
        try:
            self.total_progress_bar.setValue(value)
            self.progress_label.setText(status)
            
            # 减少UI更新频率
            if value % 5 == 0:
                self.progress_label.repaint()
                self.total_progress_bar.repaint()
                QApplication.processEvents()
                
        except Exception as e:
            print(f"Error in update_total_progress: {str(e)}")
    
    def check_chrome_history_access(self):
        """检查Chrome历史记录文件的访问权限"""
        history_path = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/History')
        
        if not os.path.exists(history_path):
            return False, "Chrome历史记录文件不存在。请确保已安装Chrome浏览器。"
            
        if not os.access(history_path, os.R_OK):
            return False, "没有读取Chrome历史记录的权限。请在系统偏好设置中授予完全磁盘访问权限。"
            
        return True, "OK"
        
    def load_history(self):
        """加载历史记录并自动开始转换"""
        # 获取用户设置的记录数量
        self.num_records = self.records_spinbox.value()
        
        # 更新UI状态
        self.progress_label.setText("正在加载历史记录...")
        self.total_progress_bar.setValue(0)
        QApplication.processEvents()
        
        # 检查访问权限
        can_access, message = self.check_chrome_history_access()
        if not can_access:
            self.progress_label.setText(f"错误: {message}")
            QMessageBox.warning(self, "访问错误", message)
            return
            
        # Chrome历史记录文件路径
        history_path = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/History')
        
        # 创建临时目录（如果不存在）
        temp_dir = os.path.expanduser('~/Library/Application Support/ChromeHistoryViewer')
        os.makedirs(temp_dir, exist_ok=True)
        
        # 在临时目录中创建历史记录文件的副本
        temp_history = os.path.join(temp_dir, 'temp_history')
        try:
            shutil.copy2(history_path, temp_history)
        except Exception as e:
            error_msg = f"复制历史记录文件失败: {str(e)}\n"
            error_msg += "可能的原因：\n"
            error_msg += "1. Chrome浏览器正在运行并锁定了历史记录文件\n"
            error_msg += "2. 没有足够的文件访问权限\n"
            error_msg += "\n解决方案：\n"
            error_msg += "1. 关闭Chrome浏览器后重试\n"
            error_msg += "2. 在系统偏好设置 > 安全性与隐私 > 完全磁盘访问权限中添加此应用"
            
            self.progress_label.setText("错误: 无法访问历史记录")
            QMessageBox.warning(self, "错误", error_msg)
            return
            
        try:
            # 连接到SQLite数据库
            conn = sqlite3.connect(temp_history)
            cursor = conn.cursor()
            
            # 查询历史记录
            cursor.execute(f'''
                SELECT title, url, last_visit_time, visit_count 
                FROM urls 
                ORDER BY last_visit_time DESC 
                LIMIT {self.num_records}
            ''')
            
            # 获取结果
            records = cursor.fetchall()
            
            # 清空现有表格
            self.table.clearContents()
            self.table.setRowCount(0)
            QApplication.processEvents()
            
            # 设置表格行数
            self.table.setRowCount(len(records))
            
            # 填充表格
            for row, record in enumerate(records):
                title = record[0] or 'No Title'
                url = record[1]
                # Chrome存储时间为自1601年1月1日以来的微秒数
                visit_time = datetime(1601, 1, 1).timestamp() + (record[2] / 1000000)
                visit_time = datetime.fromtimestamp(visit_time).strftime('%Y-%m-%d %H:%M:%S')
                visit_count = str(record[3])
                
                # 设置初始状态
                status_item = QTableWidgetItem("准备中")
                self.table.setItem(row, 0, status_item)
                
                self.table.setItem(row, 1, QTableWidgetItem(title))
                self.table.setItem(row, 2, QTableWidgetItem(url))
                self.table.setItem(row, 3, QTableWidgetItem(visit_time))
                self.table.setItem(row, 4, QTableWidgetItem(visit_count))
                
                # 每10行更新一次UI
                if row % 10 == 0:
                    QApplication.processEvents()
            
            # 调整列宽
            self.table.resizeColumnsToContents()
            
            self.progress_label.setText(f"已加载 {len(records)} 条历史记录，准备开始转换...")
            QApplication.processEvents()
            
            # 启动一个短暂的延时，然后开始转换
            QTimer.singleShot(500, self.start_conversion)
            
        except Exception as e:
            error_msg = f"读取历史记录失败: {str(e)}"
            self.progress_label.setText("错误: 读取历史记录失败")
            QMessageBox.warning(self, "错误", error_msg)
        finally:
            if 'conn' in locals():
                conn.close()
            # 删除临时文件
            if os.path.exists(temp_history):
                os.remove(temp_history)

    def toggle_monitor(self, state):
        """切换监控状态"""
        if state == Qt.Checked:
            # 启动监控
            self.monitor = HistoryMonitor(self.interval_spinbox.value())
            self.monitor.processed_urls = self.processed_urls.copy()  # 共享已处理的URL集合
            self.monitor.new_records.connect(self.process_new_records)
            self.monitor.start()
            self.interval_spinbox.setEnabled(False)
            self.progress_label.setText("监控已启动，等待新记录...")
        else:
            # 停止监控
            if self.monitor:
                self.monitor.stop()
            self.interval_spinbox.setEnabled(True)
            self.progress_label.setText("监控已停止")
    
    def process_new_records(self, new_records):
        """处理新的历史记录"""
        urls_to_process = []
        
        # 添加新记录到表格
        for record in new_records:
            title = record[0] or 'No Title'
            url = record[1]
            
            # 跳过已处理的URL
            if url in self.processed_urls:
                continue
                
            # 添加到已处理集合
            self.processed_urls.add(url)
            
            # 添加新行
            row = 0  # 在表格顶部插入新记录
            self.table.insertRow(row)
            
            # 设置状态
            status_item = QTableWidgetItem("准备中")
            status_item.setBackground(Qt.yellow)
            self.table.setItem(row, 0, status_item)
            
            # 设置其他列
            self.table.setItem(row, 1, QTableWidgetItem(title))
            self.table.setItem(row, 2, QTableWidgetItem(url))
            
            # 转换时间戳
            visit_time = datetime(1601, 1, 1).timestamp() + (record[2] / 1000000)
            visit_time = datetime.fromtimestamp(visit_time).strftime('%Y-%m-%d %H:%M:%S')
            self.table.setItem(row, 3, QTableWidgetItem(visit_time))
            
            self.table.setItem(row, 4, QTableWidgetItem(str(record[3])))
            
            # 添加到待处理列表
            urls_to_process.append((row, title, url))
            
            # 强制更新UI
            QApplication.processEvents()
        
        # 如果有新记录，开始处理
        if urls_to_process:
            # 如果当前没有下载任务在运行
            if not self.downloader or not self.downloader.is_running:
                self.downloader = WebPageDownloader(urls_to_process, self.save_dir, self.cache_monitor)
                self.downloader.progress.connect(self.update_total_progress)
                self.downloader.page_finished.connect(self.update_page_status)
                self.downloader.finished.connect(self.conversion_finished)
                self.downloader.start()
                self.stop_button.setEnabled(True)
            
            # 调整列宽并滚动到最新记录
            self.table.resizeColumnsToContents()
            self.table.scrollToTop()  # 滚动到顶部显示最新记录

    def load_processed_urls(self):
        """加载已经处理过的URL集合"""
        processed_urls = set()
        try:
            # 扫描markdown文件目录
            for file_name in os.listdir(self.save_dir):
                if file_name.endswith('.md'):
                    file_path = os.path.join(self.save_dir, file_name)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # 从文件内容中提取URL
                            url_match = re.search(r'URL: (.*?)\n', content)
                            if url_match:
                                processed_urls.add(url_match.group(1))
                    except Exception as e:
                        print(f"读取文件 {file_name} 时出错: {str(e)}")
        except Exception as e:
            print(f"加载已处理URL时出错: {str(e)}")
        return processed_urls

    def handle_cache_content(self, url, content):
        """处理从缓存获取的内容"""
        print(f"主窗口收到缓存内容: {url[:50]}...")
        if self.downloader:
            self.downloader.handle_cache_content(url, content)

def main():
    parser = argparse.ArgumentParser(description='Chrome历史记录查看和转换工具')
    parser.add_argument('--num', type=int, default=100, help='要处理的记录数量')
    parser.add_argument('--monitor', action='store_true', help='启动时自动开启监控模式')
    parser.add_argument('--interval', type=int, default=5, help='监控检查间隔（秒）')
    
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    viewer = ChromeHistoryViewer(num_records=args.num)
    
    if args.monitor:
        viewer.interval_spinbox.setValue(args.interval)
        viewer.monitor_checkbox.setChecked(True)
    
    viewer.show()
    
    def signal_handler(signum, frame):
        """处理主进程的终止信号"""
        print(f"主进程收到信号: {signum}")
        if viewer:
            viewer.force_cleanup()
        sys.exit(0)
    
    # 设置主进程的信号处理
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        sys.exit(app.exec())
    except SystemExit:
        if viewer:
            viewer.force_cleanup()
    except Exception as e:
        print(f"程序异常退出: {str(e)}")
        if viewer:
            viewer.force_cleanup()
        sys.exit(1) 