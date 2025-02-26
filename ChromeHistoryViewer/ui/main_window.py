import os
import signal
import logging
import traceback
from typing import Set, List, Tuple
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QCheckBox,
    QMessageBox, QProgressBar, QTableWidget,
    QTableWidgetItem, QApplication
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices

from ..config import (
    DEFAULT_NUM_RECORDS, DEFAULT_CHECK_INTERVAL,
    DEFAULT_SAVE_DIR, WINDOW_SIZE_RATIO,
    RAGFLOW_ENABLED, RAGFLOW_API_URL, RAGFLOW_API_KEY
)
from ..core.utils import check_chrome_access, ensure_dir
from ..core.cache_monitor import ChromeCacheMonitor
from ..core.history_monitor import HistoryMonitor
from ..core.page_downloader import WebPageDownloader

class ChromeHistoryViewer(QMainWindow):
    """Chrome历史记录查看器主窗口"""
    def __init__(self, num_records: int = DEFAULT_NUM_RECORDS):
        try:
            logging.info("初始化ChromeHistoryViewer...")
            super().__init__()
            
            # 设置信号处理
            logging.info("设置信号处理器...")
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGINT, self.signal_handler)
            
            self.setWindowTitle("Chrome History Viewer")
            logging.info("设置窗口几何属性...")
            self.setup_window_geometry()
            
            # 初始化变量
            logging.info("初始化变量...")
            self.num_records = num_records
            self.save_dir = DEFAULT_SAVE_DIR
            self.downloader = None
            self.monitor = None
            self.processed_urls: Set[str] = set()
            self._shutting_down = False
            
            # 初始化RAGFlow管理器
            self.ragflow_manager = None
            if RAGFLOW_ENABLED:
                logging.info("初始化RAGFlow管理器...")
                from ..core.ragflow_manager import RAGFlowManager
                self.ragflow_manager = RAGFlowManager(RAGFLOW_API_URL, RAGFLOW_API_KEY)
            
            # 确保保存目录存在
            logging.info(f"确保保存目录存在: {self.save_dir}")
            ensure_dir(self.save_dir)
            
            # 初始化UI
            logging.info("初始化UI组件...")
            self.init_ui()
            
            # 设置窗口标志
            self.setWindowFlags(Qt.Window)
            self.setAttribute(Qt.WA_DeleteOnClose)
            
            # 使用定时器延迟初始化缓存监控器和加载历史记录
            QTimer.singleShot(0, self.delayed_init)
            
            logging.info("ChromeHistoryViewer初始化完成")
        except Exception as e:
            logging.error("ChromeHistoryViewer初始化失败:")
            logging.error(traceback.format_exc())
            raise
        
    def setup_window_geometry(self) -> None:
        """设置窗口大小和位置"""
        screen = self.screen()
        if not screen:
            return
            
        screen_geometry = screen.availableGeometry()
        window_width = int(screen_geometry.width() * WINDOW_SIZE_RATIO)
        window_height = int(screen_geometry.height() * WINDOW_SIZE_RATIO)
        x = (screen_geometry.width() - window_width) // 2
        y = (screen_geometry.height() - window_height) // 2
        
        self.setGeometry(x, y, window_width, window_height)
        
    def delayed_init(self):
        """延迟初始化耗时操作"""
        try:
            # 初始化缓存监控器
            logging.info("初始化缓存监控器...")
            self.cache_monitor = ChromeCacheMonitor()
            self.cache_monitor.content_ready.connect(self.handle_cache_content)
            self.cache_monitor.start()
            
            # 加载历史记录
            QTimer.singleShot(100, self.load_history)
            
        except Exception as e:
            logging.error("延迟初始化失败:")
            logging.error(traceback.format_exc())
            
    def init_ui(self) -> None:
        """初始化UI组件"""
        # 创建主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 创建布局
        layout = QVBoxLayout()
        main_widget.setLayout(layout)
        
        # 添加顶部控件
        self.add_top_controls(layout)
        
        # 添加目录控件
        self.add_directory_controls(layout)
        
        # 添加进度条
        self.total_progress_bar = QProgressBar()
        layout.addWidget(self.total_progress_bar)
        
        # 添加监控控件
        self.add_monitor_controls(layout)
        
        # 创建表格
        self.create_table(layout)
        
    def add_top_controls(self, layout: QVBoxLayout) -> None:
        """添加顶部控件"""
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
        
    def add_directory_controls(self, layout: QVBoxLayout) -> None:
        """添加目录控件"""
        dir_layout = QHBoxLayout()
        
        # 添加目录标签
        dir_label = QLabel(f"保存目录: {self.save_dir}")
        dir_layout.addWidget(dir_label)
        
        # 添加打开目录按钮
        open_dir_button = QPushButton("打开目录")
        open_dir_button.clicked.connect(self.open_save_dir)
        dir_layout.addWidget(open_dir_button)
        
        # 添加停止按钮
        self.stop_button = QPushButton("停止转换")
        self.stop_button.clicked.connect(self.stop_conversion)
        self.stop_button.setEnabled(False)
        dir_layout.addWidget(self.stop_button)
        
        # 添加RAGFlow上传按钮
        if RAGFLOW_ENABLED:
            self.upload_button = QPushButton("上传到RAGFlow")
            self.upload_button.clicked.connect(self.upload_to_ragflow)
            dir_layout.addWidget(self.upload_button)
        
        dir_layout.addStretch()
        layout.addLayout(dir_layout)
        
    def add_monitor_controls(self, layout: QVBoxLayout) -> None:
        """添加监控控件"""
        monitor_layout = QHBoxLayout()
        
        # 添加监控复选框
        self.monitor_checkbox = QCheckBox("自动监控新记录")
        self.monitor_checkbox.setChecked(False)
        self.monitor_checkbox.stateChanged.connect(self.toggle_monitor)
        monitor_layout.addWidget(self.monitor_checkbox)
        
        # 添加监控间隔选择器
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 60)
        self.interval_spinbox.setValue(DEFAULT_CHECK_INTERVAL)
        self.interval_spinbox.setSuffix(" 秒")
        monitor_layout.addWidget(QLabel("检查间隔:"))
        monitor_layout.addWidget(self.interval_spinbox)
        monitor_layout.addStretch()
        
        layout.addLayout(monitor_layout)
        
    def create_table(self, layout: QVBoxLayout) -> None:
        """创建表格"""
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['状态', 'Title', 'URL', 'Visit Time', 'Visit Count'])
        layout.addWidget(self.table)
        
    def signal_handler(self, signum: int, frame) -> None:
        """处理终止信号"""
        print(f"收到信号: {signum}")
        self.force_cleanup()
        sys.exit(0)
        
    def force_cleanup(self) -> None:
        """强制清理所有资源"""
        try:
            # 停止下载器
            if hasattr(self, 'downloader') and self.downloader:
                self.downloader.is_running = False
                self.downloader.stop()
                self.downloader = None
            
            # 停止监控器
            if hasattr(self, 'monitor') and self.monitor:
                self.monitor.is_running = False
                self.monitor.stop()
                self.monitor = None
            
            # 停止缓存监控器
            if hasattr(self, 'cache_monitor') and self.cache_monitor:
                self.cache_monitor.is_running = False
                self.cache_monitor.stop()
                self.cache_monitor = None
            
            # 强制处理所有待处理的事件
            QApplication.processEvents()
            
        except Exception as e:
            print(f"强制清理时出错: {str(e)}")
            
    def closeEvent(self, event) -> None:
        """重写关闭事件，确保清理所有线程"""
        try:
            self._shutting_down = True
            self.force_cleanup()
            
            # 等待最多3秒，每100ms检查一次是否所有线程都已停止
            for _ in range(30):
                if (not hasattr(self, 'downloader') or not self.downloader) and \
                   (not hasattr(self, 'monitor') or not self.monitor) and \
                   (not hasattr(self, 'cache_monitor') or not self.cache_monitor):
                    break
                QApplication.processEvents()
                self.msleep(100)
                
        except Exception as e:
            print(f"关闭时出错: {str(e)}")
        finally:
            event.accept()
            
    def open_save_dir(self) -> None:
        """打开保存目录"""
        ensure_dir(self.save_dir)  # 确保目录存在
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.save_dir))
        
    def stop_conversion(self) -> None:
        """停止转换进程"""
        try:
            if self.downloader and self.downloader.is_running:
                self.stop_button.setEnabled(False)
                self.progress_label.setText("正在停止转换...")
                self.downloader.stop()
                self.downloader = None
                
                # 强制刷新UI
                self.repaint()
        except Exception as e:
            print(f"停止转换时出错: {str(e)}")
            
    def update_page_status(self, row: int, success: bool, message: str) -> None:
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
                
        except Exception as e:
            print(f"更新页面状态时出错: {str(e)}")
            
    def update_total_progress(self, value: int, status: str) -> None:
        """更新总体进度"""
        try:
            self.total_progress_bar.setValue(value)
            self.progress_label.setText(status)
            
            # 减少UI更新频率
            if value % 5 == 0:
                self.progress_label.repaint()
                self.total_progress_bar.repaint()
                
        except Exception as e:
            print(f"更新总进度时出错: {str(e)}")
            
    def load_history(self) -> None:
        """加载历史记录并自动开始转换"""
        try:
            # 获取用户设置的记录数量
            self.num_records = self.records_spinbox.value()
            
            # 更新UI状态
            self.progress_label.setText("正在加载历史记录...")
            self.total_progress_bar.setValue(0)
            QApplication.processEvents()
            
            # 检查访问权限
            can_access, message = check_chrome_access()
            if not can_access:
                self.progress_label.setText(f"错误: {message}")
                QMessageBox.warning(self, "访问错误", message)
                return
                
            # 获取历史记录
            history = HistoryMonitor()
            records = history.get_history_records(self.num_records)
            
            if not records:
                self.progress_label.setText("未找到历史记录")
                QMessageBox.information(self, "提示", "未找到任何历史记录。\n请确保Chrome中有浏览历史。")
                return
            
            # 清空现有表格
            self.table.clearContents()
            self.table.setRowCount(len(records))
            
            # 填充表格
            urls_to_process = []
            for row, (title, url, visit_time, visit_count) in enumerate(records):
                # 设置初始状态
                status_item = QTableWidgetItem("准备中")
                self.table.setItem(row, 0, status_item)
                
                self.table.setItem(row, 1, QTableWidgetItem(title))
                self.table.setItem(row, 2, QTableWidgetItem(url))
                self.table.setItem(row, 3, QTableWidgetItem(visit_time))
                self.table.setItem(row, 4, QTableWidgetItem(str(visit_count)))
                
                # 检查URL是否已经处理过
                if url not in self.processed_urls:
                    urls_to_process.append((row, title, url))
                else:
                    status_item = QTableWidgetItem("已存在")
                    status_item.setBackground(Qt.green)
                    self.table.setItem(row, 0, status_item)
                
                # 每10行更新一次UI
                if row % 10 == 0:
                    QApplication.processEvents()
            
            # 调整列宽
            self.table.resizeColumnsToContents()
            
            self.progress_label.setText(f"已加载 {len(records)} 条历史记录，准备开始转换...")
            
            # 启动一个短暂的延时，然后开始转换
            if urls_to_process:
                QTimer.singleShot(500, lambda: self.start_conversion(urls_to_process))
            
        except Exception as e:
            error_msg = f"读取历史记录失败: {str(e)}\n\n可能的原因：\n1. Chrome正在运行\n2. 没有足够的文件访问权限\n\n解决方案：\n1. 关闭Chrome浏览器后重试\n2. 在系统偏好设置中授予磁盘访问权限"
            self.progress_label.setText("错误: 读取历史记录失败")
            QMessageBox.warning(self, "错误", error_msg)
            
    def start_conversion(self, urls_to_process: List[Tuple[int, str, str]]) -> None:
        """开始转换所有记录"""
        if self.downloader and self.downloader.is_running:
            return
            
        # 创建并启动下载线程
        self.downloader = WebPageDownloader(urls_to_process, self.save_dir, self.cache_monitor)
        self.downloader.progress.connect(self.update_total_progress)
        self.downloader.page_finished.connect(self.update_page_status)
        self.downloader.finished.connect(self.conversion_finished)
        
        self.total_progress_bar.setValue(0)
        self.stop_button.setEnabled(True)
        self.downloader.start()
        
    def conversion_finished(self, normal_completion: bool) -> None:
        """转换完成的处理"""
        try:
            if self.downloader:
                if normal_completion:
                    self.progress_label.setText("所有页面处理完成！")
                    QMessageBox.information(self, "完成", "所有页面都已处理完成！")
                else:
                    self.progress_label.setText("转换已中断")
                
                self.stop_button.setEnabled(False)
                self.downloader = None
                
                # 强制刷新UI
                self.repaint()
                
        except Exception as e:
            print(f"转换完成处理时出错: {str(e)}")
            
    def toggle_monitor(self, state: int) -> None:
        """切换监控状态"""
        if state == Qt.Checked:
            # 启动监控
            self.monitor = HistoryMonitor(self.interval_spinbox.value())
            self.monitor.processed_urls = self.processed_urls.copy()
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
            
    def process_new_records(self, new_records: List[Tuple[str, str, int, int]]) -> None:
        """处理新的历史记录"""
        urls_to_process = []
        
        # 添加新记录到表格
        for record in new_records:
            title, url = record[0] or 'No Title', record[1]
            
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
            from ..core.utils import chrome_timestamp_to_datetime
            visit_time = chrome_timestamp_to_datetime(record[2])
            self.table.setItem(row, 3, QTableWidgetItem(visit_time.strftime('%Y-%m-%d %H:%M:%S')))
            self.table.setItem(row, 4, QTableWidgetItem(str(record[3])))
            
            # 添加到待处理列表
            urls_to_process.append((row, title, url))
            
        # 如果有新记录，开始处理
        if urls_to_process:
            # 如果当前没有下载任务在运行
            if not self.downloader or not self.downloader.is_running:
                self.start_conversion(urls_to_process)
            
            # 调整列宽并滚动到最新记录
            self.table.resizeColumnsToContents()
            self.table.scrollToTop()
            
    def upload_to_ragflow(self) -> None:
        """上传所有Markdown文件到RAGFlow"""
        if not self.ragflow_manager:
            QMessageBox.warning(self, "错误", "RAGFlow未启用，请检查配置。")
            return
            
        try:
            self.progress_label.setText("正在上传到RAGFlow...")
            QApplication.processEvents()
            
            results = self.ragflow_manager.upload_directory(self.save_dir)
            
            # 统计结果
            total = len(results)
            success = sum(1 for _, success, _ in results if success)
            
            # 显示结果
            message = f"上传完成！\n成功: {success}/{total}"
            if success < total:
                message += "\n\n失败的文件:"
                for file_path, success, error in results:
                    if not success:
                        message += f"\n{os.path.basename(file_path)}: {error}"
            
            QMessageBox.information(self, "上传结果", message)
            self.progress_label.setText(f"RAGFlow上传完成 ({success}/{total})")
            
        except Exception as e:
            error_msg = f"上传到RAGFlow失败: {str(e)}"
            logging.error(error_msg)
            QMessageBox.warning(self, "错误", error_msg)
            self.progress_label.setText("RAGFlow上传失败")

    def handle_cache_content(self, url: str, content: str) -> None:
        """处理从缓存获取的内容"""
        if self.downloader:
            self.downloader.handle_cache_content(url, content)
            
            # 如果RAGFlow已启用，尝试上传新生成的文件
            if self.ragflow_manager:
                # 查找对应的文件
                for row in range(self.table.rowCount()):
                    if self.table.item(row, 2).text() == url:
                        title = self.table.item(row, 1).text()
                        file_name = f"{get_safe_title(title, url)}.md"
                        file_path = os.path.join(self.save_dir, file_name)
                        
                        if os.path.exists(file_path):
                            try:
                                success, message = self.ragflow_manager.upload_file(file_path)
                                if success:
                                    logging.info(f"文件已上传到RAGFlow: {file_name}")
                                else:
                                    logging.error(f"上传到RAGFlow失败: {file_name} - {message}")
                            except Exception as e:
                                logging.error(f"处理RAGFlow上传时出错: {str(e)}")
                        break 