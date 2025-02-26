#!/usr/bin/env python3
import os
import sys
import time
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, Slot, QTimer

# 添加父目录到路径以便导入ChromeHistoryViewer模块
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from ChromeHistoryViewer.core.cache_monitor import ChromeCacheMonitor
from ChromeHistoryViewer.core.page_downloader import WebPageDownloader
from ChromeHistoryViewer.config import CHROME_HISTORY, CHROME_CACHE, CHROME_NETWORK

class CurrentChromeTest(QObject):
    """使用当前Chrome环境进行测试"""
    
    def __init__(self):
        super().__init__()
        self.cache_monitor = None
        self.downloader = None
        self.save_dir = os.path.join(current_dir, 'test_markdown_output')
        os.makedirs(self.save_dir, exist_ok=True)
        
        # 初始化缓存监控器
        self.init_cache_monitor()
        
    def init_cache_monitor(self):
        """初始化缓存监控器"""
        print("初始化缓存监控器...")
        self.cache_monitor = ChromeCacheMonitor()
        self.cache_monitor.content_ready.connect(self.handle_cache_content)
        self.cache_monitor.start()
        
        # 等待缓存监控器初始化
        time.sleep(2)
        
        print("缓存监控器初始化完成")
        print(f"缓存目录存在: {os.path.exists(CHROME_CACHE)}")
        print(f"网络缓存目录存在: {os.path.exists(CHROME_NETWORK)}")
        
    def get_recent_history(self, limit=10):
        """获取最近的Chrome历史记录"""
        print("\n=== 获取最近的Chrome历史记录 ===")
        
        if not os.path.exists(CHROME_HISTORY):
            print(f"Chrome历史记录文件不存在: {CHROME_HISTORY}")
            return []
            
        # 创建临时目录
        temp_dir = os.path.join(self.save_dir, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_history = os.path.join(temp_dir, 'temp_history')
        
        try:
            # 复制历史记录文件
            shutil.copy2(CHROME_HISTORY, temp_history)
            
            # 连接数据库
            conn = sqlite3.connect(temp_history)
            cursor = conn.cursor()
            
            # 查询最近的历史记录
            cursor.execute(f'''
                SELECT title, url, last_visit_time, visit_count 
                FROM urls 
                ORDER BY last_visit_time DESC 
                LIMIT {limit}
            ''')
            
            records = []
            for i, (title, url, last_visit_time, visit_count) in enumerate(cursor.fetchall()):
                # Chrome时间戳是自1601年1月1日以来的微秒数
                visit_time = datetime(1601, 1, 1) + timedelta(microseconds=last_visit_time)
                
                record = {
                    'row': i,
                    'title': title or 'No Title',
                    'url': url,
                    'visit_time': visit_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'visit_count': visit_count
                }
                records.append(record)
                
                print(f"记录 {i+1}:")
                print(f"  标题: {record['title']}")
                print(f"  URL: {record['url']}")
                print(f"  访问时间: {record['visit_time']}")
                print(f"  访问次数: {record['visit_count']}")
                print()
                
            return records
            
        except Exception as e:
            print(f"获取历史记录时出错: {str(e)}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()
            # 删除临时文件
            if os.path.exists(temp_history):
                os.remove(temp_history)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    def start_test(self):
        """开始测试过程"""
        print("\n=== 开始测试 ===")
        
        # 获取最近的历史记录
        records = self.get_recent_history(5)
        if not records:
            print("没有找到历史记录，无法继续测试")
            QTimer.singleShot(1000, self.cleanup_and_exit)
            return
            
        # 准备URL列表
        self.test_urls = [(r['row'], r['title'], r['url']) for r in records]
        print(f"测试URL: {[url for _, _, url in self.test_urls]}")
        print(f"保存目录: {self.save_dir}")
        
        # 初始化下载器
        self.downloader = WebPageDownloader(self.test_urls, self.save_dir, self.cache_monitor)
        self.downloader.progress.connect(self.update_progress)
        self.downloader.page_finished.connect(self.page_finished)
        self.downloader.finished.connect(self.test_finished)
        
        # 开始下载器
        print("\n开始下载器...")
        self.downloader.start()
        
        # 提示用户
        print("\n请注意: 测试正在进行中...")
        print("1. 测试将尝试从您的Chrome缓存中提取内容")
        print("2. 如果您最近访问过这些URL，内容可能已经在缓存中")
        print("3. 如果没有，您可以在测试运行时打开Chrome并访问这些URL")
        print("4. 测试将监控缓存变化并尝试提取内容")
        print("5. 测试将在处理完所有URL后自动结束")
    
    @Slot(str, str)
    def handle_cache_content(self, url, content):
        """处理在缓存中找到的内容"""
        print(f"\n=== 在缓存中找到URL的内容: {url} ===")
        print(f"内容长度: {len(content)}")
        print(f"内容预览: {content[:100]}...")
        
        if self.downloader:
            print("转发内容到下载器...")
            self.downloader.handle_cache_content(url, content)
    
    @Slot(int, str)
    def update_progress(self, value, status):
        """更新进度信息"""
        print(f"进度: {value}% - {status}")
    
    @Slot(int, bool, str)
    def page_finished(self, row, success, message):
        """处理页面完成事件"""
        if row < len(self.test_urls):
            url = self.test_urls[row][2]
            print(f"\n页面完成: 行 {row}, URL: {url}")
            print(f"成功: {success}, 消息: {message}")
            
            # 检查文件是否已创建
            title = self.test_urls[row][1]
            from ChromeHistoryViewer.core.utils import get_safe_title
            filename = f"{get_safe_title(title, url)}.md"
            filepath = os.path.join(self.save_dir, filename)
            
            if os.path.exists(filepath):
                print(f"文件已创建: {filepath}")
                print(f"文件大小: {os.path.getsize(filepath)} 字节")
                
                # 读取并打印部分内容
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read(500)
                    print(f"文件内容预览:\n{content}...")
                except Exception as e:
                    print(f"读取文件内容时出错: {str(e)}")
            else:
                print(f"文件未创建: {filepath}")
    
    @Slot(bool)
    def test_finished(self, normal_completion):
        """处理测试完成事件"""
        print("\n=== 测试完成 ===")
        print(f"正常完成: {normal_completion}")
        
        # 列出创建的文件
        print("\n创建的文件:")
        for filename in os.listdir(self.save_dir):
            if filename.endswith('.md'):
                filepath = os.path.join(self.save_dir, filename)
                print(f"- {filename} ({os.path.getsize(filepath)} 字节)")
        
        # 安排应用程序退出
        QTimer.singleShot(3000, self.cleanup_and_exit)
    
    def cleanup_and_exit(self):
        """清理资源并退出"""
        print("\n清理中...")
        
        if self.downloader and self.downloader.isRunning():
            print("停止下载器...")
            self.downloader.stop()
        
        if self.cache_monitor and self.cache_monitor.isRunning():
            print("停止缓存监控器...")
            self.cache_monitor.stop()
        
        print("退出应用程序")
        QApplication.quit()

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 创建并启动测试处理器
    test_handler = CurrentChromeTest()
    
    # 短暂延迟后开始测试
    QTimer.singleShot(1000, test_handler.start_test)
    
    # 运行应用程序
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 