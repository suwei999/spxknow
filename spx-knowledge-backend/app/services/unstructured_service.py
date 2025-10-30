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
                'extract_image_block_types': settings.UNSTRUCTURED_PDF_IMAGE_TYPES
            },
            'docx': {
                'strategy': settings.UNSTRUCTURED_DOCX_STRATEGY,
                'extract_images_in_pdf': settings.UNSTRUCTURED_DOCX_EXTRACT_IMAGES
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
    
    def chunk_text(self, text: str, document_type: str = "auto", chunk_size: int = None, chunk_overlap: int = None) -> List[str]:
        """文本分块 - 严格按照设计文档实现智能分块策略"""
        try:
            # 根据设计文档的分块策略配置
            strategies = {
                "semantic": {"chunk_size": 1000, "chunk_overlap": 200, "min_size": 100},
                "structure": {"chunk_size": 1500, "chunk_overlap": 150, "min_size": 200},
                "fixed": {"chunk_size": 512, "chunk_overlap": 50, "min_size": 100}
            }
            
            # 选择策略
            strategy = strategies.get(document_type, strategies["semantic"])
            
            # 使用提供的参数或默认策略
            final_chunk_size = chunk_size or strategy["chunk_size"]
            final_chunk_overlap = chunk_overlap or strategy["chunk_overlap"]
            min_size = strategy["min_size"]
            
            logger.info(f"开始文本分块，文本长度: {len(text)}, 策略: {document_type}, 分块大小: {final_chunk_size}, 重叠: {final_chunk_overlap}")
            
            # 根据设计文档的智能分块策略
            chunks = []
            
            # 按段落分割
            paragraphs = text.split('\n\n')
            current_chunk = ""
            
            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                
                # 如果当前段落加上现有分块超过大小限制
                if len(current_chunk) + len(paragraph) > final_chunk_size:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        # 添加重叠部分
                        if final_chunk_overlap > 0 and len(chunks) > 0:
                            current_chunk = chunks[-1][-final_chunk_overlap:] + "\n\n" + paragraph
                        else:
                            current_chunk = paragraph
                    else:
                        # 段落本身太长，需要进一步分割
                        sub_chunks = self._split_long_paragraph(paragraph, final_chunk_size)
                        chunks.extend(sub_chunks[:-1])  # 添加前面的完整分块
                        current_chunk = sub_chunks[-1]  # 保留最后一个不完整的分块
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + paragraph
                    else:
                        current_chunk = paragraph
            
            # 添加最后一个分块
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # 过滤空分块和小于最小尺寸的分块
            chunks = [chunk for chunk in chunks if chunk.strip() and len(chunk) >= min_size]
            
            logger.info(f"文本分块完成，共生成 {len(chunks)} 个分块")
            return chunks
            
        except Exception as e:
            logger.error(f"文本分块错误: {e}", exc_info=True)
            return [text]  # 返回原始文本作为单个分块
    
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
            # 提取文本内容
            text_content = ""
            images = []
            tables = []
            metadata = {
                'file_size': file_size,
                'file_type': os.path.splitext(file_path)[1],
                'element_count': len(elements),
                'parsing_timestamp': datetime.utcnow().isoformat() + "Z"
            }
            
            for element in elements:
                element_text = getattr(element, 'text', '')
                if element_text:
                    text_content += element_text + "\n"
                
                # 提取图片信息
                if element.category == 'Image':
                    elem_id = getattr(element, 'element_id', getattr(element, 'id', None))
                    image_info = {
                        'element_id': elem_id,
                        'image_type': 'image',
                        'page_number': _meta_get(getattr(element, 'metadata', None), 'page_number', 1),
                        'coordinates': self._extract_coordinates(element),
                        'description': element_text,
                        'ocr_text': element_text
                    }
                    images.append(image_info)
                
                # 提取表格信息
                elif element.category == 'Table':
                    elem_id = getattr(element, 'element_id', getattr(element, 'id', None))
                    table_info = {
                        'element_id': elem_id,
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
                "element_count": len(elements)
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
            # TODO: 根据设计文档，这里应该提取表格的结构化数据
            # 包括行列信息、单元格内容等
            
            table_data = {
                'rows': 0,
                'columns': 0,
                'cells': [],
                'structure': 'unknown'
            }
            
            # 临时实现 - 从文本中提取表格信息
            text = getattr(element, 'text', '')
            lines = text.split('\n')
            table_data['rows'] = len(lines)
            
            if lines:
                columns = len(lines[0].split('\t'))
                table_data['columns'] = columns
            
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
                element_metadata = getattr(element, 'metadata', {})
                
                # 提取标题（通常是第一个Title元素）
                if element.category == 'Title' and not metadata['title']:
                    metadata['title'] = getattr(element, 'text', '')
                
                # 提取作者信息
                if 'author' in element_metadata:
                    metadata['author'] = element_metadata['author']
                
                # 提取创建和修改日期
                if 'created_date' in element_metadata:
                    metadata['created_date'] = element_metadata['created_date']
                if 'modified_date' in element_metadata:
                    metadata['modified_date'] = element_metadata['modified_date']
            
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