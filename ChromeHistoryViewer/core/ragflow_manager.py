import os
import json
import logging
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path

class RAGFlowManager:
    """RAGFlow知识库管理器"""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        self.knowledge_base_id = None
        self.processed_files = set()  # 记录已处理的文件
        
        # 确保状态文件目录存在
        self.state_dir = os.path.expanduser('~/Library/Application Support/ChromeHistoryViewer/ragflow_state')
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_file = os.path.join(self.state_dir, 'processed_files.json')
        self.load_state()
        
    def load_state(self) -> None:
        """加载已处理文件的状态"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.processed_files = set(state.get('processed_files', []))
                    self.knowledge_base_id = state.get('knowledge_base_id')
        except Exception as e:
            logging.error(f"加载RAGFlow状态文件失败: {str(e)}")
            
    def save_state(self) -> None:
        """保存处理状态"""
        try:
            state = {
                'processed_files': list(self.processed_files),
                'knowledge_base_id': self.knowledge_base_id,
                'last_update': datetime.now().isoformat()
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存RAGFlow状态文件失败: {str(e)}")
            
    def ensure_knowledge_base(self, name: str = "Chrome History") -> str:
        """确保知识库存在，返回知识库ID"""
        if self.knowledge_base_id:
            return self.knowledge_base_id
            
        try:
            # 创建知识库
            response = requests.post(
                f"{self.api_url}/api/v1/knowledge-bases",
                headers=self.headers,
                json={'name': name}
            )
            response.raise_for_status()
            self.knowledge_base_id = response.json()['id']
            
            # 配置知识库
            config_response = requests.post(
                f"{self.api_url}/api/v1/knowledge-bases/{self.knowledge_base_id}/config",
                headers=self.headers,
                json={
                    'embedding_model': 'text-embedding-v2',  # 使用默认的嵌入模型
                    'chunk_method': 'markdown'  # 使用markdown模板
                }
            )
            config_response.raise_for_status()
            
            self.save_state()
            return self.knowledge_base_id
            
        except Exception as e:
            logging.error(f"创建知识库失败: {str(e)}")
            raise
            
    def upload_file(self, file_path: str) -> Tuple[bool, str]:
        """上传单个文件到知识库"""
        try:
            # 检查文件是否已处理
            if file_path in self.processed_files:
                return True, "文件已存在"
                
            # 确保知识库存在
            kb_id = self.ensure_knowledge_base()
            
            # 上传文件
            with open(file_path, 'rb') as f:
                files = {'file': (os.path.basename(file_path), f, 'text/markdown')}
                response = requests.post(
                    f"{self.api_url}/api/v1/knowledge-bases/{kb_id}/files",
                    headers={'Authorization': f'Bearer {self.api_key}'},
                    files=files
                )
                response.raise_for_status()
                
            # 获取文件ID
            file_id = response.json()['id']
            
            # 开始解析
            parse_response = requests.post(
                f"{self.api_url}/api/v1/knowledge-bases/{kb_id}/files/{file_id}/parse",
                headers=self.headers
            )
            parse_response.raise_for_status()
            
            # 记录已处理的文件
            self.processed_files.add(file_path)
            self.save_state()
            
            return True, "上传成功"
            
        except Exception as e:
            logging.error(f"上传文件失败 {file_path}: {str(e)}")
            return False, str(e)
            
    def upload_directory(self, directory: str) -> List[Tuple[str, bool, str]]:
        """上传目录中的所有Markdown文件"""
        results = []
        try:
            for file in Path(directory).glob('*.md'):
                success, message = self.upload_file(str(file))
                results.append((str(file), success, message))
        except Exception as e:
            logging.error(f"上传目录失败 {directory}: {str(e)}")
        return results
        
    def check_file_status(self, file_id: str) -> Dict:
        """检查文件处理状态"""
        try:
            kb_id = self.ensure_knowledge_base()
            response = requests.get(
                f"{self.api_url}/api/v1/knowledge-bases/{kb_id}/files/{file_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"检查文件状态失败 {file_id}: {str(e)}")
            return {'status': 'ERROR', 'message': str(e)} 