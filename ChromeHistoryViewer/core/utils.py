import os
import shutil
import unicodedata
import re
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple

def clean_filename(title: str) -> Optional[str]:
    """清理文件名，使其在所有操作系统上都安全可用"""
    if not title:
        return None
        
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
    if len(title.encode('utf-8')) > 250:  # 文件系统通常限制255字节
        while len(title.encode('utf-8')) > 250:
            title = title[:-1]
    
    return title

def get_safe_title(title: str, url: str) -> str:
    """获取安全的文件标题，如果标题无效则使用URL的哈希值"""
    safe_title = clean_filename(title)
    if not safe_title:
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        safe_title = f"untitled_{url_hash}"
    return safe_title

def copy_file_safe(src: str, dst: str) -> bool:
    """安全地复制文件，确保目标目录存在"""
    try:
        dst_dir = os.path.dirname(dst)
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except Exception as e:
        print(f"复制文件失败: {str(e)}")
        return False

def chrome_timestamp_to_datetime(timestamp: int) -> datetime:
    """将Chrome的时间戳转换为datetime对象"""
    # Chrome时间戳是自1601年1月1日以来的微秒数
    return datetime(1601, 1, 1) + timedelta(microseconds=timestamp)

def ensure_dir(directory: str) -> bool:
    """确保目录存在，如果不存在则创建"""
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except Exception as e:
        print(f"创建目录失败: {str(e)}")
        return False

def check_chrome_access() -> Tuple[bool, str]:
    """检查Chrome相关文件的访问权限"""
    from ..config import CHROME_HISTORY, CHROME_CACHE, CHROME_COOKIES
    
    # 检查Chrome目录是否存在
    chrome_dir = os.path.dirname(CHROME_HISTORY)
    if not os.path.exists(chrome_dir):
        return False, f"Chrome配置目录不存在: {chrome_dir}\n请确保已安装Chrome浏览器。"
        
    # 检查历史记录文件
    if not os.path.exists(CHROME_HISTORY):
        return False, "Chrome历史记录文件不存在。\n请确保已安装Chrome浏览器并有浏览历史。"
        
    if not os.access(CHROME_HISTORY, os.R_OK):
        return False, "没有读取Chrome历史记录的权限。\n请在系统偏好设置中授予完全磁盘访问权限。"
        
    # 尝试复制历史记录文件
    try:
        temp_dir = os.path.expanduser('~/Library/Application Support/ChromeHistoryViewer/temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_history = os.path.join(temp_dir, 'test_history')
        
        import shutil
        try:
            shutil.copy2(CHROME_HISTORY, temp_history)
            os.remove(temp_history)
        except (IOError, PermissionError):
            # 如果直接复制失败，尝试使用sqlite3复制
            import sqlite3
            conn = sqlite3.connect(CHROME_HISTORY)
            backup_conn = sqlite3.connect(temp_history)
            conn.backup(backup_conn)
            conn.close()
            backup_conn.close()
            os.remove(temp_history)
            
    except Exception as e:
        return False, f"无法访问Chrome历史记录文件: {str(e)}\n请确保已授予磁盘访问权限。"
        
    return True, "OK" 