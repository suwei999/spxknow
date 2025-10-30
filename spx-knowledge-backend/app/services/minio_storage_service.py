"""
MinIO Storage Service
根据文档处理流程设计实现MinIO文件存储功能
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional, BinaryIO
from minio import Minio
from minio.error import S3Error
from fastapi import UploadFile
from app.config.settings import settings
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode

class MinioStorageService:
    """MinIO存储服务 - 严格按照设计文档实现存储结构"""
    
    def __init__(self):
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            secure=settings.MINIO_SECURE
        )
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """确保存储桶存在"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"创建MinIO存储桶: {self.bucket_name}")
            else:
                logger.debug(f"MinIO存储桶已存在: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"MinIO存储桶操作失败: {e}")
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"MinIO存储桶操作失败: {str(e)}"
            )
    
    def generate_storage_path(self, file_hash: str, filename: str, file_type: str) -> str:
        """生成存储路径 - 根据设计文档的存储结构"""
        try:
            # 根据设计文档的存储路径设计：
            # documents/2024/01/doc_123456/original.pdf
            # documents/2024/01/doc_123456/parsed/content.json
            # documents/2024/01/doc_123456/parsed/chunks/
            # documents/2024/01/doc_123456/parsed/images/
            # documents/2024/01/doc_123456/parsed/tables/
            # documents/2024/01/doc_123456/metadata.json
            
            now = datetime.now()
            year = now.strftime("%Y")
            month = now.strftime("%m")
            
            # 使用文件哈希作为文档ID
            doc_id = f"doc_{file_hash[:8]}"
            
            # 原始文件路径
            original_path = f"documents/{year}/{month}/{doc_id}/original.{file_type.lower()}"
            
            logger.debug(f"生成存储路径: {original_path}")
            return original_path
            
        except Exception as e:
            logger.error(f"生成存储路径错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"生成存储路径失败: {str(e)}"
            )
    
    def upload_original_file(self, file: UploadFile, file_hash: str) -> Dict[str, Any]:
        """上传原始文件 - 根据设计文档实现"""
        try:
            logger.info(f"开始上传原始文件: {file.filename}")
            
            # 生成存储路径
            file_extension = os.path.splitext(file.filename)[1][1:]  # 去掉点号
            object_name = self.generate_storage_path(file_hash, file.filename, file_extension)
            
            # 重置文件指针
            file.file.seek(0)
            file_content = file.file.read()
            file.file.seek(0)
            
            # 上传到MinIO
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=file.file,
                length=len(file_content),
                content_type=file.content_type
            )
            
            result = {
                "success": True,
                "object_name": object_name,
                "bucket_name": self.bucket_name,
                "file_size": len(file_content),
                "content_type": file.content_type,
                "upload_timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"原始文件上传成功: {object_name}")
            return result
            
        except S3Error as e:
            logger.error(f"MinIO上传错误: {e}")
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"文件上传失败: {str(e)}"
            )
        except Exception as e:
            logger.error(f"文件上传错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"文件上传失败: {str(e)}"
            )
    
    def upload_parsed_content(self, document_id: str, content: Dict[str, Any]) -> Dict[str, Any]:
        """上传解析后的内容 - 根据设计文档实现"""
        try:
            logger.info(f"开始上传解析内容: {document_id}")
            
            import json
            from io import BytesIO
            
            # 生成解析内容路径
            now = datetime.now()
            year = now.strftime("%Y")
            month = now.strftime("%m")
            content_path = f"documents/{year}/{month}/{document_id}/parsed/content.json"
            
            # 转换为JSON
            content_json = json.dumps(content, ensure_ascii=False, indent=2)
            content_bytes = content_json.encode('utf-8')
            
            # 上传解析内容
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=content_path,
                data=BytesIO(content_bytes),
                length=len(content_bytes),
                content_type="application/json"
            )
            
            result = {
                "success": True,
                "content_path": content_path,
                "content_size": len(content_bytes)
            }
            
            logger.info(f"解析内容上传成功: {content_path}")
            return result
            
        except Exception as e:
            logger.error(f"解析内容上传错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"解析内容上传失败: {str(e)}"
            )
    
    def upload_chunks(self, document_id: str, chunks: list) -> Dict[str, Any]:
        """上传分块数据 - JSONL.GZ 归档，便于回灌与降本"""
        try:
            logger.info(f"开始上传分块数据: {document_id}")
            
            import json
            import gzip
            from io import BytesIO
            
            # 生成分块路径
            now = datetime.now()
            year = now.strftime("%Y")
            month = now.strftime("%m")
            chunks_path = f"documents/{year}/{month}/{document_id}/parsed/chunks/chunks.jsonl.gz"
            
            # 按行写 JSONL，并使用 gzip 压缩
            buf = BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb') as gz:
                for idx, c in enumerate(chunks):
                    line = json.dumps({"index": idx, "content": c}, ensure_ascii=False).encode('utf-8')
                    gz.write(line + b"\n")
            chunks_bytes = buf.getvalue()
            
            # 上传分块数据
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=chunks_path,
                data=BytesIO(chunks_bytes),
                length=len(chunks_bytes),
                content_type="application/gzip"
            )
            
            result = {
                "success": True,
                "chunks_path": chunks_path,
                "chunks_count": len(chunks),
                "chunks_size": len(chunks_bytes)
            }
            
            logger.info(f"分块数据上传成功(JSONL.GZ): {chunks_path}, 共 {len(chunks)} 个分块")
            return result
            
        except Exception as e:
            logger.error(f"分块数据上传错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"分块数据上传失败: {str(e)}"
            )
    
    def upload_images(self, document_id: str, images: list) -> Dict[str, Any]:
        """上传图片数据 - 根据设计文档实现"""
        try:
            logger.info(f"开始上传图片数据: {document_id}")
            
            import json
            from io import BytesIO
            
            # 生成图片路径
            now = datetime.now()
            year = now.strftime("%Y")
            month = now.strftime("%m")
            images_path = f"documents/{year}/{month}/{document_id}/parsed/images/images.json"
            
            # 转换为JSON
            images_json = json.dumps(images, ensure_ascii=False, indent=2)
            images_bytes = images_json.encode('utf-8')
            
            # 上传图片数据
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=images_path,
                data=BytesIO(images_bytes),
                length=len(images_bytes),
                content_type="application/json"
            )
            
            result = {
                "success": True,
                "images_path": images_path,
                "images_count": len(images),
                "images_size": len(images_bytes)
            }
            
            logger.info(f"图片数据上传成功: {images_path}, 共 {len(images)} 张图片")
            return result
            
        except Exception as e:
            logger.error(f"图片数据上传错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"图片数据上传失败: {str(e)}"
            )
    
    def upload_metadata(self, document_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """上传元数据 - 根据设计文档实现"""
        try:
            logger.info(f"开始上传元数据: {document_id}")
            
            import json
            from io import BytesIO
            
            # 生成元数据路径
            now = datetime.now()
            year = now.strftime("%Y")
            month = now.strftime("%m")
            metadata_path = f"documents/{year}/{month}/{document_id}/metadata.json"
            
            # 转换为JSON
            metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
            metadata_bytes = metadata_json.encode('utf-8')
            
            # 上传元数据
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=metadata_path,
                data=BytesIO(metadata_bytes),
                length=len(metadata_bytes),
                content_type="application/json"
            )
            
            result = {
                "success": True,
                "metadata_path": metadata_path,
                "metadata_size": len(metadata_bytes)
            }
            
            logger.info(f"元数据上传成功: {metadata_path}")
            return result
            
        except Exception as e:
            logger.error(f"元数据上传错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"元数据上传失败: {str(e)}"
            )
    
    def download_file(self, object_name: str) -> bytes:
        """下载文件 - 根据设计文档实现"""
        try:
            logger.info(f"开始下载文件: {object_name}")
            
            response = self.client.get_object(self.bucket_name, object_name)
            file_content = response.read()
            response.close()
            response.release_conn()
            
            logger.info(f"文件下载成功: {object_name}, 大小: {len(file_content)} bytes")
            return file_content
            
        except S3Error as e:
            logger.error(f"MinIO下载错误: {e}")
            raise CustomException(
                code=ErrorCode.MINIO_DOWNLOAD_FAILED,
                message=f"文件下载失败: {str(e)}"
            )
        except Exception as e:
            logger.error(f"文件下载错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.MINIO_DOWNLOAD_FAILED,
                message=f"文件下载失败: {str(e)}"
            )
    
    def delete_file(self, object_name: str) -> bool:
        """删除文件 - 根据设计文档实现"""
        try:
            logger.info(f"开始删除文件: {object_name}")
            
            self.client.remove_object(self.bucket_name, object_name)
            
            logger.info(f"文件删除成功: {object_name}")
            return True
            
        except S3Error as e:
            logger.error(f"MinIO删除错误: {e}")
            return False
        except Exception as e:
            logger.error(f"文件删除错误: {e}", exc_info=True)
            return False
    
    def list_files(self, prefix: str = "") -> list:
        """列出文件 - 根据设计文档实现"""
        try:
            logger.info(f"开始列出文件: {prefix}")
            
            objects = self.client.list_objects(
                bucket_name=self.bucket_name,
                prefix=prefix,
                recursive=True
            )
            
            file_list = []
            for obj in objects:
                file_list.append({
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag
                })
            
            logger.info(f"文件列表获取成功: {len(file_list)} 个文件")
            return file_list
            
        except Exception as e:
            logger.error(f"文件列表获取错误: {e}", exc_info=True)
            return []

    # =============== 通用字节上传（用于图片等二进制） ===============
    def upload_bytes(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """上传任意二进制到指定对象名，返回对象路径。"""
        from io import BytesIO
        try:
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            logger.info(f"二进制上传成功: {object_name} ({len(data)} bytes)")
            return object_name
        except S3Error as e:
            logger.error(f"MinIO上传错误: {e}")
            raise CustomException(
                code=ErrorCode.MINIO_UPLOAD_FAILED,
                message=f"文件上传失败: {str(e)}",
            )