import sys
import argparse
import logging
import traceback
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from .config import DEFAULT_NUM_RECORDS, DEFAULT_CHECK_INTERVAL
from .ui.main_window import ChromeHistoryViewer

def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    """程序主入口"""
    setup_logging()
    logging.info("程序启动...")
    
    try:
        # 启用Qt调试输出
        logging.info("启用Qt调试输出...")
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
        
        logging.info("解析命令行参数...")
        parser = argparse.ArgumentParser(description='Chrome历史记录查看和转换工具')
        parser.add_argument('--num', type=int, default=DEFAULT_NUM_RECORDS, help='要处理的记录数量')
        parser.add_argument('--monitor', action='store_true', help='启动时自动开启监控模式')
        parser.add_argument('--interval', type=int, default=DEFAULT_CHECK_INTERVAL, help='监控检查间隔（秒）')
        
        args = parser.parse_args()
        logging.info(f"参数解析完成: {args}")
        
        logging.info("初始化QApplication...")
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        logging.info("QApplication初始化完成")
        
        try:
            logging.info("创建主窗口...")
            viewer = ChromeHistoryViewer(num_records=args.num)
            
            if args.monitor:
                logging.info("启用监控模式...")
                viewer.interval_spinbox.setValue(args.interval)
                viewer.monitor_checkbox.setChecked(True)
            
            logging.info("显示主窗口...")
            viewer.show()
            viewer.raise_()  # 将窗口提升到最前
            viewer.activateWindow()  # 激活窗口
            
            logging.info("进入主事件循环...")
            return_code = app.exec()
            logging.info(f"主事件循环结束，返回码: {return_code}")
            return return_code
            
        except Exception as e:
            logging.error("创建或显示主窗口时出错:")
            logging.error(traceback.format_exc())
            return 1
            
    except Exception as e:
        logging.error("程序初始化时出错:")
        logging.error(traceback.format_exc())
        return 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        logging.error("程序异常退出:")
        logging.error(traceback.format_exc())
        sys.exit(1) 