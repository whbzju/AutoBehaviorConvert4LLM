import os
import sqlite3
import shutil
from typing import List, Set, Tuple, Optional
from PySide6.QtCore import QThread, Signal
import time
import logging

from ..config import CHROME_HISTORY, TEMP_DIR
from ..core.utils import chrome_timestamp_to_datetime, copy_file_safe

class HistoryMonitor(QThread):
    """监控Chrome历史记录更新的线程"""
    new_records = Signal(list)  # 发送新记录的信号
    
    def __init__(self, check_interval: int = 5):
        super().__init__()
        self.check_interval = check_interval  # 检查间隔（秒）
        self.last_check_time: Optional[int] = None
        self.is_running = False
        self.processed_urls: Set[str] = set()  # 记录已处理的URL
        
    def get_new_records(self) -> List[Tuple[str, str, int, int]]:
        """获取新的历史记录"""
        temp_history = os.path.join(TEMP_DIR, 'temp_history_monitor')
        
        try:
            # 复制历史记录文件
            if not copy_file_safe(CHROME_HISTORY, temp_history):
                return []
            
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

    def run(self) -> None:
        """运行监控线程"""
        try:
            self.is_running = True
            while self.is_running:
                try:
                    new_records = self.get_new_records()
                    if new_records:
                        self.new_records.emit(new_records)
                except Exception as e:
                    print(f"监控线程错误: {str(e)}")
                    self.msleep(1000)  # 出错时等待1秒再重试
                    continue
                
                # 等待下次检查，但每秒检查是否需要停止
                for _ in range(self.check_interval):
                    if not self.is_running:
                        break
                    self.msleep(1000)
                    
        except Exception as e:
            print(f"历史记录监控线程出错: {str(e)}")
        finally:
            self.is_running = False
    
    def stop(self) -> None:
        """停止监控线程"""
        self.is_running = False
        self.wait(1000)  # 最多等待1秒
        if self.isRunning():
            self.terminate()  # 强制终止
            self.wait()

    def get_history_records(self, limit: int = 100) -> List[Tuple[str, str, str, int]]:
        """获取历史记录"""
        temp_history = os.path.join(TEMP_DIR, 'temp_history')
        records = []
        
        try:
            # 尝试复制历史记录文件
            try:
                shutil.copy2(CHROME_HISTORY, temp_history)
            except (IOError, PermissionError):
                # 如果直接复制失败，尝试使用sqlite3复制
                conn = sqlite3.connect(CHROME_HISTORY)
                backup_conn = sqlite3.connect(temp_history)
                conn.backup(backup_conn)
                conn.close()
                backup_conn.close()
            
            # 连接数据库
            conn = sqlite3.connect(temp_history)
            cursor = conn.cursor()
            
            # 查询历史记录
            cursor.execute(f'''
                SELECT title, url, last_visit_time, visit_count 
                FROM urls 
                ORDER BY last_visit_time DESC 
                LIMIT {limit}
            ''')
            
            # 处理结果
            for record in cursor.fetchall():
                title = record[0] or 'No Title'
                url = record[1]
                visit_time = chrome_timestamp_to_datetime(record[2])
                visit_time_str = visit_time.strftime('%Y-%m-%d %H:%M:%S')
                visit_count = record[3]
                
                records.append((title, url, visit_time_str, visit_count))
            
        except Exception as e:
            logging.error(f"读取历史记录失败: {str(e)}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()
            if os.path.exists(temp_history):
                try:
                    os.remove(temp_history)
                except:
                    pass
                
        return records 