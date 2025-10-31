"""
Unstructured Service
根据文档处理流程设计实现Unstructured文档解析功能
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import UploadFile
import os
import tempfile
import json
import zipfile
from unstructured.partition.auto import partition
from unstructured.staging.base import elements_to_json
from app.core.logging import logger
from app.config.settings import settings
from app.services.office_converter import convert_docx_to_pdf
from app.core.exceptions import CustomException, ErrorCode
import xml.etree.ElementTree as ET
import io

class UnstructuredService:
    """Unstructured文档解析服务 - 严格按照设计文档实现"""
    
    def __init__(self, db: Session):
        self.db = db
        # 注入 Poppler 到 PATH（Windows 常见问题）
        try:
            if settings.POPPLER_PATH:
                poppler_bin = settings.POPPLER_PATH
                if os.path.isdir(poppler_bin) and poppler_bin not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = poppler_bin + os.pathsep + os.environ.get('PATH', '')
                    os.environ.setdefault('POPPLER_PATH', poppler_bin)
                    logger.info(f"已注入 POPPLER_PATH 到环境: {poppler_bin}")
            # 注入 Tesseract（可选）
            if getattr(settings, 'TESSERACT_PATH', None):
                tess_bin = settings.TESSERACT_PATH
                if os.path.isdir(tess_bin) and tess_bin not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = tess_bin + os.pathsep + os.environ.get('PATH', '')
                    logger.info(f"已注入 TESSERACT_PATH 到环境: {tess_bin}")
            if getattr(settings, 'TESSDATA_PREFIX', None):
                os.environ.setdefault('TESSDATA_PREFIX', settings.TESSDATA_PREFIX)
                logger.info(f"设置 TESSDATA_PREFIX: {settings.TESSDATA_PREFIX}")
        except Exception as e:
            logger.warning(f"注入 POPPLER_PATH 失败: {e}")
        # 根据设计文档的解析策略配置 - 从settings读取
        self.parsing_strategies = {
            'pdf': {
                'strategy': settings.UNSTRUCTURED_PDF_STRATEGY,
                'ocr_languages': settings.UNSTRUCTURED_PDF_OCR_LANGUAGES,
                'extract_images_in_pdf': settings.UNSTRUCTURED_PDF_EXTRACT_IMAGES,
                'extract_image_block_types': settings.UNSTRUCTURED_PDF_IMAGE_TYPES,
                # 高保真解析增强：启用表格结构、元数据、中文识别
                'infer_table_structure': True,
                'include_metadata': True,
                'languages': getattr(settings, 'UNSTRUCTURED_LANGUAGES', ['zh', 'en'])
            },
            'docx': {
                'strategy': settings.UNSTRUCTURED_DOCX_STRATEGY,
                'extract_images_in_pdf': settings.UNSTRUCTURED_DOCX_EXTRACT_IMAGES,
                # 对 Office 文档同样启用结构与元数据提取（未被支持的参数将被忽略）
                'infer_table_structure': True,
                'include_metadata': True,
                'languages': getattr(settings, 'UNSTRUCTURED_LANGUAGES', ['zh', 'en'])
            },
            'pptx': {
                'strategy': settings.UNSTRUCTURED_PPTX_STRATEGY,
                'extract_images_in_pdf': settings.UNSTRUCTURED_PPTX_EXTRACT_IMAGES
            },
            'html': {
                'strategy': settings.UNSTRUCTURED_HTML_STRATEGY,
                'extract_images_in_pdf': settings.UNSTRUCTURED_HTML_EXTRACT_IMAGES
            },
            'txt': {
                'strategy': 'fast',
                'encoding': settings.UNSTRUCTURED_TXT_ENCODING
            }
        }
        # 自动检测设备/框架能力
        if settings.UNSTRUCTURED_AUTO_DEVICE:
            try:
                import torch  # type: ignore
                torch_version = getattr(torch, '__version__', 'unknown')
                use_cuda = torch.cuda.is_available()
                os.environ.setdefault('UNSTRUCTURED_DEVICE', 'cuda' if use_cuda else 'cpu')
                logger.info(f"Unstructured 设备: {'CUDA' if use_cuda else 'CPU'}, torch={torch_version}")
                # 若配置了 hi_res 且 torch 版本过低，自动降级
                from packaging import version
                if torch_version != 'unknown' and version.parse(torch_version) < version.parse('2.1.0'):
                    if self.parsing_strategies['pdf'].get('strategy') == 'hi_res':
                        self.parsing_strategies['pdf']['strategy'] = 'fast'
                        logger.warning("检测到 torch<2.1，PDF hi_res 自动降级为 fast")
            except Exception as _e:
                logger.warning(f"未检测到 torch 或自动设备配置失败: {_e}. 将使用 fast/CPU 流程。")
    
    def _select_parsing_strategy(self, file_type: str) -> str:
        """选择解析策略 - 根据设计文档实现"""
        file_type = file_type.lower() if file_type else "unknown"
        
        # 根据设计文档的解析策略选择
        strategy_map = {
            'pdf': 'hi_res',  # 高分辨率解析、OCR、图片提取
            'docx': 'fast',    # 快速解析、图片提取
            'pptx': 'fast',    # 快速解析、图片提取
            'html': 'fast',    # 快速解析、图片提取
            'txt': 'fast',     # 快速解析
            'unknown': 'auto'  # 自动选择
        }
        
        return strategy_map.get(file_type, 'auto')

    def _validate_docx_integrity(self, file_path: str) -> None:
        """DOCX 解析前的完整性校验：必须是合法 OOXML zip，且包含核心条目。
        不通过直接抛业务异常（不降级）。"""
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                names = set(zf.namelist())
        except Exception as e:
            raise CustomException(
                code=ErrorCode.DOCUMENT_PARSING_FAILED,
                message=f"DOCX 文件不是有效的 ZIP（可能已损坏）: {e}"
            )
        required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
        missing = [n for n in required if n not in names]
        if missing:
            raise CustomException(
                code=ErrorCode.DOCUMENT_PARSING_FAILED,
                message=f"DOCX 结构缺少核心条目: {', '.join(missing)}（文件可能由非标准工具导出或已损坏）"
            )
        # 深度校验：rels 中不应引用 NULL，且引用的部件必须存在
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # 1) 禁止任何条目名为 'NULL'
                upper_names = {name.upper() for name in zf.namelist()}
                if 'NULL' in upper_names:
                    raise CustomException(
                        code=ErrorCode.DOCUMENT_PARSING_FAILED,
                        message="DOCX 包含非法部件名 'NULL'，文件已损坏或导出不规范"
                    )
                # 2) 扫描所有 .rels，检查 Target
                rels_files = [n for n in zf.namelist() if n.endswith('.rels')]
                for rel_path in rels_files:
                    with zf.open(rel_path) as fp:
                        tree = ET.parse(fp)
                        root = tree.getroot()
                        # 关系命名空间常见为 http://schemas.openxmlformats.org/package/2006/relationships
                        for rel in root.findall('.//{*}Relationship'):
                            target = rel.get('Target') or ''
                            if target.strip().upper() == 'NULL':
                                raise CustomException(
                                    code=ErrorCode.DOCUMENT_PARSING_FAILED,
                                    message=f"DOCX 关系文件 {rel_path} 引用了非法 Target='NULL'（文件损坏/导出不规范）"
                                )
                            # 仅校验相对路径目标是否存在
                            if not (target.startswith('http://') or target.startswith('https://')):
                                # 归一化成 zip 内部路径
                                base_dir = rel_path.rsplit('/', 1)[0] if '/' in rel_path else ''
                                normalized = f"{base_dir}/{target}" if base_dir else target
                                normalized = normalized.replace('\\', '/').lstrip('./')
                                if normalized and normalized not in zf.namelist():
                                    # 某些目标可能是上级目录，如 ../word/media/image1.png，做一次简单归一化
                                    while normalized.startswith('../'):
                                        normalized = normalized[3:]
                                    if normalized not in zf.namelist():
                                        raise CustomException(
                                            code=ErrorCode.DOCUMENT_PARSING_FAILED,
                                            message=f"DOCX 引用了缺失的部件: {target}（来源 {rel_path}）"
                                        )
        except CustomException:
            raise
        except Exception as e:
            # 校验过程异常，按解析失败处理，给出明确提示
            raise CustomException(
                code=ErrorCode.DOCUMENT_PARSING_FAILED,
                message=f"DOCX 结构校验失败: {e}"
            )
    
    def _attempt_docx_repair(self, file_path: str) -> Optional[str]:
        """尝试自动修复常见 DOCX 关系错误（officeDocument 关系指向 NULL 或缺失）。
        修复成功返回新 docx 临时路径，否则返回 None。"""
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                names = set(zf.namelist())
                if "_rels/.rels" not in names:
                    return None
                candidates = [n for n in names if n.startswith('word/document') and n.endswith('.xml')]
                if not candidates:
                    return None
                target_part = 'word/document.xml' if 'word/document.xml' in names else sorted(candidates)[0]
                with zf.open('_rels/.rels') as fp:
                    tree = ET.parse(fp)
                root = tree.getroot()
                modified = False
                for rel in root.findall('.{*}Relationship'):
                    pass
                for rel in root.findall('.//{*}Relationship'):
                    r_type = rel.get('Type') or ''
                    if r_type.endswith('/officeDocument'):
                        cur = (rel.get('Target') or '').strip()
                        normalized = cur.replace('\\','/').lstrip('./')
                        if cur.upper() == 'NULL' or normalized not in names:
                            rel.set('Target', target_part)
                            modified = True
                if not modified:
                    return None
                fd, tmp_path = tempfile.mkstemp(suffix='.docx')
                os.close(fd)
                with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as out:
                    for name in zf.namelist():
                        if name == '_rels/.rels':
                            buf = io.BytesIO()
                            tree.write(buf, encoding='utf-8', xml_declaration=True)
                            out.writestr(name, buf.getvalue())
                        else:
                            out.writestr(name, zf.read(name))
                logger.warning(f"DOCX 已自动修复 officeDocument 关系 -> {target_part}，修复文件: {tmp_path}")
                return tmp_path
        except Exception as e:
            logger.error(f"尝试修复 DOCX 失败: {e}")
            return None

    def parse_document(self, file_path: str, strategy: Optional[str] = None) -> Dict[str, Any]:
        """解析文档 - 严格按照设计文档实现（Unstructured 失败将直接抛错，不做降级）"""
        try:
            logger.info(f"开始解析文档: {file_path}")
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                raise CustomException(
                    code=ErrorCode.FILE_NOT_FOUND,
                    message=f"文件不存在: {file_path}"
                )
            
            # 获取文件信息
            file_size = os.path.getsize(file_path)
            file_extension = os.path.splitext(file_path)[1].lower()
            logger.info(f"文件大小: {file_size} bytes, 扩展名: {file_extension}")
            
            # 根据文件类型选择解析策略
            file_type = self._get_file_type(file_extension)
            strategy_config = self.parsing_strategies.get(file_type, {})
            
            # 如果提供了strategy参数，使用它
            if strategy:
                strategy_config['strategy'] = strategy
            
            logger.info(f"使用解析策略: {file_type}, 配置: {strategy_config}")
            
            # DOCX：尝试修复/清洗；若仍失败可选转 PDF 再解析
            path_for_parse = file_path
            if file_type == 'docx':
                if settings.ENABLE_DOCX_REPAIR:
                    logger.info("[DOCX] 尝试自动修复主文档关系与无效引用…")
                    repaired = self._attempt_docx_repair(file_path)
                    if repaired:
                        path_for_parse = repaired
                        logger.info(f"[DOCX] 修复成功，使用修复后的临时文件: {path_for_parse}")
                    else:
                        logger.info("[DOCX] 未进行修复或无需修复，继续校验。")
                try:
                    logger.info(f"[DOCX] 开始完整性校验: {path_for_parse}")
                    self._validate_docx_integrity(path_for_parse)
                    logger.info("[DOCX] 完整性校验通过。")
                except CustomException as e:
                    logger.error(f"[DOCX] 完整性校验失败: {e}")
                    if settings.ENABLE_OFFICE_TO_PDF:
                        logger.info("[DOCX] 启用 LibreOffice 兜底：开始 DOCX→PDF 转换…")
                        pdf_path = convert_docx_to_pdf(path_for_parse)
                        if not pdf_path:
                            logger.error("[DOCX] LibreOffice 转换失败，无法继续解析。")
                            raise
                        file_type = 'pdf'
                        path_for_parse = pdf_path
                        strategy_config = self.parsing_strategies.get(file_type, {})
                        logger.info(f"[DOCX] 转换为 PDF 成功，改用 PDF 管线解析: {path_for_parse}")
                    else:
                        raise
            
            # 仅使用 Unstructured；任何异常将直接抛出
            logger.info(f"调用 Unstructured.partition，文件={path_for_parse}，配置={strategy_config}")
            elements = partition(filename=path_for_parse, **strategy_config)
            
            logger.info(f"Unstructured解析完成，提取到 {len(elements)} 个元素")
            
            # 处理解析结果
            result = self._process_parsed_elements(elements, file_path, file_size)
            
            logger.info(f"文档解析完成，提取到 {len(result.get('text_content', ''))} 字符")
            return result
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"文档解析错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.DOCUMENT_PARSING_FAILED,
                message=f"文档解析失败: {str(e)}"
            )
    
    def extract_images(self, file_path: str) -> List[Dict[str, Any]]:
        """提取图片 - 严格按照设计文档实现"""
        try:
            logger.info(f"开始提取图片: {file_path}")
            
            # 使用Unstructured提取图片
            elements = partition(
                filename=file_path,
                extract_images_in_pdf=True,
                extract_image_block_types=['Image', 'Table']
            )
            
            images = []
            for i, element in enumerate(elements):
                if element.category == 'Image':
                    image_info = {
                        'image_id': f"img_{i+1:03d}",
                        'element_id': element.element_id,
                        'image_type': 'image',
                        'page_number': getattr(element, 'metadata', {}).get('page_number', 1),
                        'coordinates': self._extract_coordinates(element),
                        'description': getattr(element, 'text', ''),
                        'ocr_text': getattr(element, 'text', ''),
                        'element_type': element.category
                    }
                    images.append(image_info)
                elif element.category == 'Table':
                    # 表格转图片
                    table_info = {
                        'image_id': f"table_{i+1:03d}",
                        'element_id': element.element_id,
                        'image_type': 'table',
                        'page_number': getattr(element, 'metadata', {}).get('page_number', 1),
                        'coordinates': self._extract_coordinates(element),
                        'description': '表格内容',
                        'ocr_text': getattr(element, 'text', ''),
                        'element_type': element.category,
                        'table_data': self._extract_table_data(element)
                    }
                    images.append(table_info)
            
            logger.info(f"图片提取完成，共提取到 {len(images)} 张图片")
            return images
            
        except Exception as e:
            logger.error(f"图片提取错误: {e}", exc_info=True)
            return []
    
    def extract_tables(self, file_path: str) -> List[Dict[str, Any]]:
        """提取表格 - 严格按照设计文档实现"""
        try:
            logger.info(f"开始提取表格: {file_path}")
            
            # 使用Unstructured提取表格
            elements = partition(
                filename=file_path,
                extract_image_block_types=['Table']
            )
            
            tables = []
            for i, element in enumerate(elements):
                if element.category == 'Table':
                    table_info = {
                        'table_id': f"table_{i+1:03d}",
                        'element_id': element.element_id,
                        'page_number': getattr(element, 'metadata', {}).get('page_number', 1),
                        'coordinates': self._extract_coordinates(element),
                        'table_data': self._extract_table_data(element),
                        'table_text': getattr(element, 'text', ''),
                        'element_type': element.category
                    }
                    tables.append(table_info)
            
            logger.info(f"表格提取完成，共提取到 {len(tables)} 个表格")
            return tables
            
        except Exception as e:
            logger.error(f"表格提取错误: {e}", exc_info=True)
            return []
    
    def chunk_text(self, text: str, document_type: str = "auto", chunk_size: int = None, chunk_overlap: int = None, 
                   text_element_index_map: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        文本分块 - 严格按照设计文档实现智能分块策略
        返回格式：List[Dict] 包含 {'content': str, 'element_index_start': int, 'element_index_end': int}
        """
        try:
            # 根据设计文档的分块策略配置
            strategies = {
                "semantic": {"chunk_size": 1000, "chunk_overlap": 200, "min_size": 100},
                "structure": {"chunk_size": 1500, "chunk_overlap": 150, "min_size": 200},
                "fixed": {"chunk_size": 512, "chunk_overlap": 50, "min_size": 100}
            }
            
            # 选择策略
            strategy = strategies.get(document_type, strategies["semantic"])
            
            # 使用提供的参数或默认策略，并与模型上限对齐，避免后续向量化截断
            from app.config.settings import settings as _settings
            model_max = int(getattr(_settings, 'TEXT_EMBED_MAX_CHARS', 1024))
            proposed = chunk_size or strategy["chunk_size"]
            final_chunk_size = min(proposed, model_max)
            final_chunk_overlap = chunk_overlap or strategy["chunk_overlap"]
            min_size = strategy["min_size"]
            
            logger.info(f"开始文本分块，文本长度: {len(text)}, 策略: {document_type}, 分块大小: {final_chunk_size}, 重叠: {final_chunk_overlap}")
            
            # 根据设计文档的智能分块策略
            chunks = []
            current_chunk = ""
            current_chunk_start_pos = 0  # 当前分块在 text_content 中的起始位置
            
            # 按段落分割
            paragraphs = text.split('\n\n')
            
            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                
                # 如果当前段落加上现有分块超过大小限制
                if len(current_chunk) + len(paragraph) > final_chunk_size:
                    if current_chunk:
                        # 计算当前分块覆盖的 element_index 范围
                        chunk_end_pos = current_chunk_start_pos + len(current_chunk)
                        element_index_start, element_index_end = self._get_element_index_range(
                            current_chunk_start_pos, chunk_end_pos, text_element_index_map
                        )
                        chunks.append({
                            'content': current_chunk.strip(),
                            'element_index_start': element_index_start,
                            'element_index_end': element_index_end
                        })
                        
                        # 添加重叠部分
                        if final_chunk_overlap > 0 and len(chunks) > 0:
                            # 计算重叠部分的起始位置
                            overlap_start_pos = chunk_end_pos - final_chunk_overlap
                            overlap_element_start, _ = self._get_element_index_range(
                                overlap_start_pos, chunk_end_pos, text_element_index_map
                            )
                            current_chunk = chunks[-1]['content'][-final_chunk_overlap:] + "\n\n" + paragraph
                            current_chunk_start_pos = overlap_start_pos  # 重叠部分的起始位置
                        else:
                            current_chunk = paragraph
                            current_chunk_start_pos = chunk_end_pos + 2  # +2 for \n\n
                    else:
                        # 段落本身太长，需要进一步分割
                        sub_chunks = self._split_long_paragraph(paragraph, final_chunk_size)
                        # 处理前面的完整分块
                        for sub_chunk in sub_chunks[:-1]:
                            chunk_end_pos = current_chunk_start_pos + len(sub_chunk)
                            element_index_start, element_index_end = self._get_element_index_range(
                                current_chunk_start_pos, chunk_end_pos, text_element_index_map
                            )
                            chunks.append({
                                'content': sub_chunk.strip(),
                                'element_index_start': element_index_start,
                                'element_index_end': element_index_end
                            })
                            current_chunk_start_pos = chunk_end_pos + 2  # +2 for \n\n
                        # 保留最后一个不完整的分块
                        current_chunk = sub_chunks[-1]
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + paragraph
                    else:
                        current_chunk = paragraph
            
            # 添加最后一个分块
            if current_chunk:
                chunk_end_pos = current_chunk_start_pos + len(current_chunk)
                element_index_start, element_index_end = self._get_element_index_range(
                    current_chunk_start_pos, chunk_end_pos, text_element_index_map
                )
                chunks.append({
                    'content': current_chunk.strip(),
                    'element_index_start': element_index_start,
                    'element_index_end': element_index_end
                })
            
            # 过滤空分块和小于最小尺寸的分块
            chunks = [chunk for chunk in chunks if chunk.get('content', '').strip() and len(chunk.get('content', '')) >= min_size]
            
            logger.info(f"文本分块完成，共生成 {len(chunks)} 个分块")
            
            # 兼容旧接口：如果没有提供 text_element_index_map，返回纯字符串列表
            if text_element_index_map is None:
                return [chunk['content'] if isinstance(chunk, dict) else chunk for chunk in chunks]
            
            return chunks
            
        except Exception as e:
            logger.error(f"文本分块错误: {e}", exc_info=True)
            # 错误时返回原始文本作为单个分块
            if text_element_index_map:
                element_index_start = text_element_index_map[0]['element_index'] if text_element_index_map else 0
                element_index_end = text_element_index_map[-1]['element_index'] if text_element_index_map else 0
                return [{'content': text, 'element_index_start': element_index_start, 'element_index_end': element_index_end}]
            return [text]
    
    def _get_element_index_range(self, start_pos: int, end_pos: int, 
                                 text_element_index_map: Optional[List[Dict[str, Any]]]) -> tuple:
        """
        根据文本位置范围，计算对应的 element_index 范围
        返回: (element_index_start, element_index_end)
        """
        if not text_element_index_map:
            return (None, None)
        
        element_indices = []
        for map_item in text_element_index_map:
            map_start = map_item.get('start_pos', 0)
            map_end = map_item.get('end_pos', 0)
            # 如果文本段落的范围与分块范围有重叠
            if not (map_end < start_pos or map_start > end_pos):
                element_indices.append(map_item.get('element_index'))
        
        if not element_indices:
            return (None, None)
        
        return (min(element_indices), max(element_indices))
    
    def _get_file_type(self, file_extension: str) -> str:
        """获取文件类型"""
        extension_map = {
            '.pdf': 'pdf',
            '.docx': 'docx',
            '.pptx': 'pptx',
            '.html': 'html',
            '.htm': 'html',
            '.txt': 'txt',
            '.md': 'txt',
            '.csv': 'txt',
            '.json': 'txt',
            '.xml': 'txt'
        }
        return extension_map.get(file_extension, 'txt')
    
    def _process_parsed_elements(self, elements: List, file_path: str, file_size: int) -> Dict[str, Any]:
        """处理解析后的元素"""
        try:
            def _meta_get(meta_obj: Any, key: str, default: Any = None):
                if meta_obj is None:
                    return default
                # ElementMetadata 场景
                val = getattr(meta_obj, key, None)
                if val is not None:
                    return val
                # 兼容 dict
                if isinstance(meta_obj, dict):
                    return meta_obj.get(key, default)
                # 兼容提供 to_dict()
                to_dict = getattr(meta_obj, 'to_dict', None)
                if callable(to_dict):
                    try:
                        d = to_dict()
                        if isinstance(d, dict):
                            return d.get(key, default)
                    except Exception:
                        pass
                return default
            # 提取文本内容和元素索引映射（用于100%还原文档顺序）
            text_content = ""
            images = []
            tables = []
            # 文本元素索引映射：记录每个文本段落在 text_content 中的位置范围对应的 element_index
            text_element_index_map = []  # [(start_pos, end_pos, element_index), ...]
            current_text_pos = 0
            metadata = {
                'file_size': file_size,
                'file_type': os.path.splitext(file_path)[1],
                'element_count': len(elements),
                'parsing_timestamp': datetime.utcnow().isoformat() + "Z"
            }
            
            # 遍历所有元素，记录 element_index（用于100%还原文档顺序）
            import re
            for element_index, element in enumerate(elements):
                element_text = getattr(element, 'text', '')
                # 基础清洗：去除回车、合并多空格、修复被换行打断的行
                if element_text:
                    element_text = element_text.replace('\r', '')
                    # 连续空格/制表符归一
                    element_text = re.sub(r"[\t\f\v]+", " ", element_text)
                    element_text = re.sub(r"[ ]{2,}", " ", element_text)
                
                # 处理文本元素（包括 Title, NarrativeText, ListItem 等）
                if element_text and element.category not in ['Image', 'Table']:
                    text_start_pos = current_text_pos
                    text_end_pos = current_text_pos + len(element_text)
                    text_content += element_text + "\n"
                    # 记录文本段落的 element_index 映射
                    text_element_index_map.append({
                        'start_pos': text_start_pos,
                        'end_pos': text_end_pos - 1,  # 减去换行符
                        'element_index': element_index,
                        'element_type': element.category,
                        'page_number': _meta_get(getattr(element, 'metadata', None), 'page_number', None),
                        'coordinates': self._extract_coordinates(element)
                    })
                    current_text_pos = text_end_pos + 1  # +1 for \n
                
                # 提取图片信息（记录 element_index）
                elif element.category == 'Image':
                    elem_id = getattr(element, 'element_id', getattr(element, 'id', None))
                    # 尝试从 Unstructured 元数据中取出图片二进制（base64）
                    data_bytes = None
                    image_ext = '.png'
                    try:
                        meta_obj = getattr(element, 'metadata', None)
                        # 常见字段：image_base64 / image_bytes / binary / data 等
                        b64 = None
                        for key in ('image_base64', 'image_data', 'data', 'binary'):
                            val = getattr(meta_obj, key, None)
                            if val is None and isinstance(meta_obj, dict):
                                val = meta_obj.get(key)
                            if val:
                                b64 = val
                                break
                        if not b64:
                            # 某些实现可能把base64放在 element 自身
                            for key in ('image_base64', 'image_data', 'data', 'binary'):
                                val = getattr(element, key, None)
                                if val:
                                    b64 = val
                                    break
                        if b64:
                            from app.utils.conversion_utils import base64_to_bytes
                            data_bytes = base64_to_bytes(b64)
                        else:
                            # 尝试从 element.image (PIL) 导出
                            pil_img = getattr(element, 'image', None)
                            if pil_img is not None:
                                try:
                                    from io import BytesIO
                                    buf = BytesIO()
                                    pil_img.save(buf, format='PNG')
                                    data_bytes = buf.getvalue()
                                    image_ext = '.png'
                                except Exception:
                                    data_bytes = None
                        # 进一步兜底：有些解析器仅给出磁盘临时文件路径
                        if not data_bytes and meta_obj is not None:
                            for path_key in ('image_path', 'file_path', 'filename', 'png_path', 'path'):
                                p = getattr(meta_obj, path_key, None)
                                if p is None and isinstance(meta_obj, dict):
                                    p = meta_obj.get(path_key)
                                if p and isinstance(p, str) and os.path.exists(p):
                                    try:
                                        with open(p, 'rb') as f:
                                            data_bytes = f.read()
                                        # 根据扩展名设置 ext
                                        _, ext = os.path.splitext(p)
                                        if ext:
                                            image_ext = ext.lower()
                                        break
                                    except Exception:
                                        pass
                    except Exception:
                        data_bytes = None

                    image_info = {
                        'element_id': elem_id,
                        'element_index': element_index,  # 关键：记录元素在原始elements中的索引
                        'image_type': 'image',
                        'page_number': _meta_get(getattr(element, 'metadata', None), 'page_number', 1),
                        'coordinates': self._extract_coordinates(element),
                        'description': element_text,
                        'ocr_text': element_text
                    }
                    # 提供给后续流水线的二进制与扩展名（若可用）
                    if data_bytes:
                        image_info['data'] = data_bytes
                        image_info['ext'] = image_ext
                    images.append(image_info)
                
                # 提取表格信息（记录 element_index）
                elif element.category == 'Table':
                    elem_id = getattr(element, 'element_id', getattr(element, 'id', None))
                    table_info = {
                        'element_id': elem_id,
                        'element_index': element_index,  # 关键：记录元素在原始elements中的索引
                        'page_number': _meta_get(getattr(element, 'metadata', None), 'page_number', 1),
                        'coordinates': self._extract_coordinates(element),
                        'table_data': self._extract_table_data(element),
                        'table_text': element_text
                    }
                    tables.append(table_info)
            
            # 提取文档属性
            doc_metadata = self._extract_document_metadata(elements)
            metadata.update(doc_metadata)
            
            result = {
                "text_content": text_content.strip(),
                "images": images,
                "tables": tables,
                "metadata": metadata,
                "char_count": len(text_content),
                "word_count": len(text_content.split()),
                "element_count": len(elements),
                # 新增：文本元素索引映射（用于100%还原文档顺序）
                "text_element_index_map": text_element_index_map
            }
            
            return result
            
        except Exception as e:
            logger.error(f"处理解析元素错误: {e}", exc_info=True)
            return {
                "text_content": "",
                "images": [],
                "tables": [],
                "metadata": {"error": str(e)},
                "char_count": 0,
                "word_count": 0,
                "element_count": 0
            }
    
    def _extract_coordinates(self, element) -> Dict[str, Any]:
        """提取元素坐标信息"""
        try:
            metadata = getattr(element, 'metadata', None)
            coordinates = None
            if metadata is not None:
                coordinates = getattr(metadata, 'coordinates', None)
                if coordinates is None and isinstance(metadata, dict):
                    coordinates = metadata.get('coordinates')
            
            if coordinates:
                # 兼容对象/字典两种结构
                if isinstance(coordinates, dict):
                    return {
                        'x': coordinates.get('x', 0),
                        'y': coordinates.get('y', 0),
                        'width': coordinates.get('width', 0),
                        'height': coordinates.get('height', 0)
                    }
                # 对象场景，尽量读取可用字段
                return {
                    'x': getattr(coordinates, 'x', 0),
                    'y': getattr(coordinates, 'y', 0),
                    'width': getattr(coordinates, 'width', 0),
                    'height': getattr(coordinates, 'height', 0)
                }
            else:
                return {
                    'x': 0,
                    'y': 0,
                    'width': 0,
                    'height': 0
                }
        except Exception as e:
            logger.error(f"提取坐标信息错误: {e}")
            return {'x': 0, 'y': 0, 'width': 0, 'height': 0}
    
    def _extract_table_data(self, element) -> Dict[str, Any]:
        """提取表格数据"""
        try:
            # 优先从元数据中提取 HTML/结构化信息，兜底从文本拆分
            table_data: Dict[str, Any] = {
                'rows': 0,
                'columns': 0,
                'cells': [],
                'structure': 'unknown'
            }

            # 1) 尝试提取 HTML 片段（便于前端原样预览）
            html = getattr(element, 'text_as_html', None)
            if not html:
                meta = getattr(element, 'metadata', None)
                candidate_keys = ('text_as_html', 'table_html', 'html', 'text_html')
                if meta is not None:
                    for k in candidate_keys:
                        val = getattr(meta, k, None)
                        if val is None and isinstance(meta, dict):
                            val = meta.get(k)
                        if val:
                            html = val
                            break
            if html:
                table_data['html'] = html

            # 2) 兜底：将表格文本按 \n / \t 拆分成二维数组
            text = getattr(element, 'text', '') or ''
            if text:
                lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
                cells: List[List[str]] = []
                for ln in lines:
                    cols = [c.strip() for c in ln.split('\t')]
                    cells.append(cols)
                if cells:
                    table_data['cells'] = cells
                    table_data['rows'] = len(cells)
                    table_data['columns'] = max((len(r) for r in cells), default=0)
                    table_data['structure'] = 'tsv'

            return table_data
            
        except Exception as e:
            logger.error(f"提取表格数据错误: {e}")
            return {'rows': 0, 'columns': 0, 'cells': [], 'structure': 'unknown'}
    
    def _extract_document_metadata(self, elements: List) -> Dict[str, Any]:
        """提取文档元数据"""
        try:
            metadata = {
                'title': '',
                'author': '',
                'created_date': '',
                'modified_date': '',
                'language': 'unknown',
                'keywords': [],
                'entities': []
            }
            
            # 从元素中提取元数据
            for element in elements:
                element_metadata = getattr(element, 'metadata', None)
                
                # 提取标题（通常是第一个Title元素）
                if element.category == 'Title' and not metadata['title']:
                    metadata['title'] = getattr(element, 'text', '')
                
                # 提取作者/时间信息（兼容 ElementMetadata/dict/None）
                try:
                    def _safe_get(obj, key, default=None):
                        if obj is None:
                            return default
                        val = getattr(obj, key, None)
                        if val is not None:
                            return val
                        if isinstance(obj, dict):
                            return obj.get(key, default)
                        to_dict = getattr(obj, 'to_dict', None)
                        if callable(to_dict):
                            try:
                                d = to_dict()
                                if isinstance(d, dict):
                                    return d.get(key, default)
                            except Exception:
                                return default
                        return default
                    author = _safe_get(element_metadata, 'author', None)
                    if author:
                        metadata['author'] = author
                    created_date = _safe_get(element_metadata, 'created_date', None)
                    if created_date:
                        metadata['created_date'] = created_date
                    modified_date = _safe_get(element_metadata, 'modified_date', None)
                    if modified_date:
                        metadata['modified_date'] = modified_date
                except Exception:
                    pass
            
            return metadata
            
        except Exception as e:
            logger.error(f"提取文档元数据错误: {e}")
            return {
                'title': '',
                'author': '',
                'created_date': '',
                'modified_date': '',
                'language': 'unknown',
                'keywords': [],
                'entities': []
            }
    
    def _split_long_paragraph(self, paragraph: str, chunk_size: int) -> List[str]:
        """分割过长的段落"""
        try:
            chunks = []
            sentences = paragraph.split('。')
            current_chunk = ""
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                if len(current_chunk) + len(sentence) > chunk_size:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        # 句子本身太长，按字符分割
                        char_chunks = [sentence[i:i+chunk_size] for i in range(0, len(sentence), chunk_size)]
                        chunks.extend(char_chunks[:-1])
                        current_chunk = char_chunks[-1]
                else:
                    if current_chunk:
                        current_chunk += "。" + sentence
                    else:
                        current_chunk = sentence
            
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            return chunks
            
        except Exception as e:
            logger.error(f"分割长段落错误: {e}")
            return [paragraph]