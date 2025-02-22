import os
import html2text
from typing import List, Tuple, Dict
from PySide6.QtCore import QThread, Signal

from ..config import DEFAULT_SAVE_DIR, BATCH_SIZE
from ..core.utils import get_safe_title, ensure_dir

class WebPageDownloader(QThread):
    """网页下载和转换线程"""
    progress = Signal(int, str)  # 进度百分比, 状态信息
    page_finished = Signal(int, bool, str)  # 行号, 是否成功, 消息
    finished = Signal(bool)  # 是否正常完成
    
    def __init__(self, urls: List[Tuple[int, str, str]], save_dir: str = DEFAULT_SAVE_DIR, cache_monitor=None):
        super().__init__()
        self.urls = urls
        self.save_dir = save_dir
        self.converter = html2text.HTML2Text()
        self.configure_converter()
        self.is_running = False
        self.cache_monitor = cache_monitor
        self.pending_urls: Dict[int, Tuple[str, str]] = {}  # row -> (title, url)
        
        # 确保保存目录存在
        ensure_dir(self.save_dir)
        
    def configure_converter(self) -> None:
        """配置HTML到Markdown的转换器"""
        self.converter.unicode_snob = True
        self.converter.body_width = 0
        self.converter.ignore_images = False
        self.converter.ignore_emphasis = False
        self.converter.ignore_links = False
        self.converter.protect_links = True
        self.converter.mark_code = True
        
    def run(self) -> None:
        """运行下载线程"""
        self.is_running = True
        total = len(self.urls)
        completed = 0
        
        # 先扫描一遍缓存目录
        if self.cache_monitor:
            self.cache_monitor.scan_existing_cache()
        
        # 按批次处理URL
        for i in range(0, len(self.urls), BATCH_SIZE):
            if not self.is_running:
                self.finished.emit(False)
                return
                
            batch = self.urls[i:i + BATCH_SIZE]
            
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
                    file_path = os.path.join(self.save_dir, f"{get_safe_title(title, url)}.md")
                    
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

    def save_as_markdown(self, row: int, title: str, url: str, html_content: str, source: str) -> None:
        """保存为Markdown文件"""
        try:
            file_path = os.path.join(self.save_dir, f"{get_safe_title(title, url)}.md")
            
            # 转换为Markdown
            markdown_content = f"# {title}\n\nURL: {url}\n来源: {source}\n\n---\n\n"
            markdown_content += self.converter.handle(html_content)
            
            # 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            self.page_finished.emit(row, True, f"完成({source})")
            
        except Exception as e:
            raise Exception(f"保存Markdown失败: {str(e)}")

    def handle_cache_content(self, url: str, content: str) -> None:
        """处理从缓存获取的内容"""
        # 查找对应的行号和标题
        for row, (title, pending_url) in self.pending_urls.items():
            if url == pending_url:
                try:
                    self.save_as_markdown(row, title, url, content, "缓存")
                    del self.pending_urls[row]
                except Exception as e:
                    self.page_finished.emit(row, False, str(e))
                break

    def stop(self) -> None:
        """停止下载进程"""
        self.is_running = False
        self.wait()  # 等待线程结束 