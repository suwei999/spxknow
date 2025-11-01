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
import re
import shutil
from unstructured.partition.auto import partition
from unstructured.staging.base import elements_to_json
from app.core.logging import logger
from app.config.settings import settings
from app.services.office_converter import convert_docx_to_pdf
from app.core.exceptions import CustomException, ErrorCode
from app.utils.download_progress import (
    log_download_start, 
    log_download_success, 
    log_download_error
)
import xml.etree.ElementTree as ET
import io

# 预编译常用正则表达式（性能优化）
_RE_WHITESPACE = re.compile(r'\s+')
_RE_TABS = re.compile(r"[\t\f\v]+")
_RE_MULTI_SPACES = re.compile(r"[ ]{2,}")
_RE_CHINESE = re.compile(r'[\u4e00-\u9fff]')
_RE_CHARS_ONLY = re.compile(r'[a-zA-Z\u4e00-\u9fff\d]')
_RE_PUNCTUATION = re.compile(r'[^\w\s\u4e00-\u9fff]')
_RE_RANDOM_CHARS = re.compile(r'[^a-zA-Z\u4e00-\u9fff\s]{3,}')

# 预编译通用内容保护正则表达式（性能优化）
_RE_SECTION_SINGLE = re.compile(r'^\d+\.')  # 单数字加点
_RE_SECTION_MULTI = re.compile(r'\d+\.\d+(?:\.\d+)*')  # 多级编号
_RE_SECTION_CHINESE = re.compile(r'[一二三四五六七八九十]+[\.、]')  # 中文编号
_RE_SECTION_ROMAN = re.compile(r'[IVX]+\.\d+')  # 罗马数字
_RE_SECTION_CHAPTER = re.compile(r'第[一二三四五六七八九十\d]+[章节条]')  # 章节文字
_RE_SECTION_PART = re.compile(r'第[一二三四五六七八九十\d]+[部分篇]')  # 部分/篇
_RE_APPENDIX_EN = re.compile(r'Appendix\s+[A-Z\d]', re.IGNORECASE)  # Appendix A/1
_RE_APPENDIX_CN = re.compile(r'Appendix\s+[一二三四五六七八九十]', re.IGNORECASE)  # Appendix 一
_RE_CHINESE_5_CHARS = re.compile(r'[\u4e00-\u9fa5]{5,}')  # 5个以上连续汉字
_RE_ENGLISH_WORD = re.compile(r'\b[a-zA-Z]{3,}\b')  # 3个以上字母的单词

# 常量定义
DEFAULT_PAGE_HEIGHT = 842  # A4高度（点）
MIN_TEXT_LENGTH_FOR_DUPLICATE = 10
MIN_TEXT_LENGTH_FOR_NOISE = 5
MIN_TEXT_LENGTH_FOR_NOISE_PDF = 3
MAX_PREVIOUS_TEXTS = 50
MAX_DUPLICATE_CHECK = 10

class UnstructuredService:
    """Unstructured文档解析服务 - 严格按照设计文档实现"""
    
    def __init__(self, db: Session):
        self.db = db
        
        # 配置 Hugging Face 模型路径（优先使用本地模型，本地没有则联网下载）
        try:
            hf_home = settings.HF_HOME or settings.UNSTRUCTURED_MODELS_DIR
            # ✅ 关键：强制设置所有 HF 相关的环境变量，确保只使用配置的目录
            os.environ['HF_HOME'] = hf_home  # 强制覆盖，不使用 setdefault
            transformers_cache = os.path.join(hf_home, 'transformers_cache')
            datasets_cache = os.path.join(hf_home, 'datasets_cache')
            
            # ✅ 关键：设置 HF_HUB_CACHE，强制 huggingface_hub 使用配置的缓存目录
            # HF_HUB_CACHE 是 huggingface_hub 库的主要缓存路径
            hf_hub_cache = os.path.join(hf_home, 'hub')
            os.environ['TRANSFORMERS_CACHE'] = transformers_cache  # 强制覆盖
            os.environ['HF_DATASETS_CACHE'] = datasets_cache  # 强制覆盖
            os.environ['HF_HUB_CACHE'] = hf_hub_cache  # ✅ 新增：强制 huggingface_hub 使用配置的缓存
            
            # 确保所有模型目录自动创建
            os.makedirs(hf_home, exist_ok=True)
            os.makedirs(transformers_cache, exist_ok=True)
            os.makedirs(datasets_cache, exist_ok=True)
            os.makedirs(hf_hub_cache, exist_ok=True)  # ✅ 新增：创建 HF Hub 缓存目录
            
            logger.info(f"✅ 已强制设置 Hugging Face 缓存目录（不再使用默认 ~/.cache/huggingface）:")
            logger.info(f"   HF_HOME={hf_home}")
            logger.info(f"   HF_HUB_CACHE={hf_hub_cache}")
            logger.info(f"   TRANSFORMERS_CACHE={transformers_cache}")
            
            # YOLOX 模型路径配置（unstructured 库使用的布局检测模型）
            # 模型路径：models/unstructured/yolo_x_layout/yolox_10.05.onnx
            yolo_model_dir = os.path.join(settings.UNSTRUCTURED_MODELS_DIR, 'yolo_x_layout')
            yolo_model_path = os.path.join(yolo_model_dir, 'yolox_10.05.onnx')
            
            # 确保 YOLOX 模型目录自动创建
            os.makedirs(yolo_model_dir, exist_ok=True)
            
            # ⚠️ 重要：检查模型是否已存在（包括指定路径和HF缓存目录）
            # unstructured 库下载的模型可能缓存在 HF 缓存目录中
            model_found = False
            model_location = None
            
            def _check_model_in_directory(directory, desc=""):
                """在指定目录中查找 YOLOX 模型"""
                if not os.path.exists(directory):
                    return None
                try:
                    for root, dirs, files in os.walk(directory):
                        for file in files:
                            if file.endswith('.onnx') and ('yolo' in file.lower() or 'layout' in file.lower()):
                                cached_model_path = os.path.join(root, file)
                                # 检查文件大小（YOLOX模型通常>1MB）
                                try:
                                    file_size = os.path.getsize(cached_model_path)
                                    if file_size > 1024 * 1024:  # 至少1MB
                                        return cached_model_path
                                except OSError:
                                    continue
                except Exception:
                    pass
                return None
            
            # ✅ 模型检查顺序（严格按照要求）：
            # 1. 首先检查指定路径（settings.py 配置的本地路径）
            # 2. 然后检查配置的缓存目录（settings.py 配置的缓存目录）
            # 3. 如果都没有，准备联网下载到配置的缓存目录
            
            # 1. 优先检查指定路径（最优先）
            if os.path.exists(yolo_model_path):
                model_found = True
                model_location = yolo_model_path
                # ✅ 关键：设置环境变量，强制 unstructured 库使用本地模型，不访问网络
                os.environ['UNSTRUCTURED_LAYOUT_MODEL'] = yolo_model_path
                logger.info(f"✅ 步骤1: 在指定路径找到本地模型，使用: {yolo_model_path}")
            else:
                # 2. 检查配置的 Hugging Face 缓存目录（第二步）
                # 注意：只检查 settings.py 配置的缓存目录，不检查默认的 ~/.cache/huggingface
                cached_model = _check_model_in_directory(transformers_cache, "配置的缓存目录")
                if cached_model:
                    model_found = True
                    model_location = cached_model
                    # ✅ 关键：设置环境变量，强制 unstructured 库使用缓存中的模型
                    os.environ['UNSTRUCTURED_LAYOUT_MODEL'] = cached_model
                    logger.info(f"✅ 步骤2: 在配置的缓存目录中发现模型: {cached_model}")
                    logger.info(f"✅ 已设置 UNSTRUCTURED_LAYOUT_MODEL 环境变量，强制使用本地缓存，不会访问网络")
                else:
                    # 3. 模型不存在于配置的位置，准备下载到配置的缓存目录
                    logger.info(f"⚠️ 步骤3: 模型未在配置的位置找到，将联网下载到: {transformers_cache}")
                    logger.info(f"   配置的缓存目录: {transformers_cache}")
                    logger.info(f"   配置的 HF_HOME: {hf_home}")
                    # 模型将在调用 partition 时下载到配置的缓存目录
            
            # ✅ 关键：如果找到了模型，设置离线模式，避免网络请求
            if model_found and model_location:
                # 设置 HF_HUB_OFFLINE=1，强制使用本地缓存，不访问网络
                os.environ.setdefault('HF_HUB_OFFLINE', '1')
                logger.debug(f"✅ 已设置 HF_HUB_OFFLINE=1，禁用 Hugging Face 网络请求")
            
            if not model_found:
                # 设置 Hugging Face 下载进度显示（无论是否允许下载都设置，以便后续使用）
                try:
                    os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '0')
                    from huggingface_hub.utils import disable_progress_bars
                    disable_progress_bars(False)
                except Exception:
                    pass
                
                if settings.UNSTRUCTURED_AUTO_DOWNLOAD_MODEL:
                    logger.info(f"⚠️ 本地 YOLOX 模型不存在: {yolo_model_path}")
                    logger.info("📥 已启用自动下载，首次使用 hi_res 策略时将自动从 Hugging Face 下载模型")
                    logger.info(f"💾 下载后的模型将保存到缓存目录: {transformers_cache}")
                    # 注意：实际下载会在 partition 调用时（使用 hi_res 策略）才发生
                    # 模型下载后会缓存在 HF_HOME 目录下
                else:
                    logger.warning(f"⚠️ 本地 YOLOX 模型不存在: {yolo_model_path}")
                    logger.warning("❌ UNSTRUCTURED_AUTO_DOWNLOAD_MODEL=False，禁止自动下载")
                    logger.warning("💡 请手动下载模型或设置 UNSTRUCTURED_AUTO_DOWNLOAD_MODEL=True")
            
            logger.info(f"📁 Hugging Face 模型目录: {hf_home}")
            logger.info(f"📁 Transformers 缓存目录: {transformers_cache}")
        except Exception as e:
            logger.error(f"❌ 配置 Hugging Face 模型路径失败: {e}", exc_info=True)
        
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
        """
        解析文档 - 严格按照设计文档实现（Unstructured 失败将直接抛错，不做降级）
        
        注意：
        1. 如果DOCX不完整会转换为PDF，生成的临时文件会在解析完成后自动清理
        2. 转换后的PDF路径会返回在result['converted_pdf_path']中，调用者负责保存到MinIO
        """
        # 跟踪需要清理的临时文件（修复的DOCX、转换的PDF及其临时目录）
        temp_files_to_cleanup = []  # 临时文件路径列表
        temp_dirs_to_cleanup = []   # 临时目录路径列表
        original_file_path = file_path  # 保存原始文件路径，用于最终返回结果
        
        try:
            logger.info(f"开始解析文档: {file_path}")
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                raise CustomException(
                    code=ErrorCode.FILE_NOT_FOUND,
                    message=f"文件不存在: {file_path}"
                )
            
            # 获取文件信息（使用原始文件）
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
                repaired_docx_path = None
                if settings.ENABLE_DOCX_REPAIR:
                    logger.info("[DOCX] 尝试自动修复主文档关系与无效引用…")
                    repaired_docx_path = self._attempt_docx_repair(file_path)
                    if repaired_docx_path:
                        path_for_parse = repaired_docx_path
                        temp_files_to_cleanup.append(repaired_docx_path)  # 标记为需要清理的临时文件
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
                        
                        # PDF转换成功，记录PDF路径（但不立即清理，由调用者负责）
                        file_type = 'pdf'
                        path_for_parse = pdf_path
                        # 重要：转换后的PDF不立即清理，需要在保存到MinIO后再清理
                        # PDF文件会返回给调用者，由调用者决定何时清理
                        pdf_dir = os.path.dirname(pdf_path)
                        # PDF文件本身不加入清理列表（由调用者负责）
                        # 但PDF目录需要跟踪，以便在异常情况下也能清理（通过调用者的finally块）
                        # 注意：正常流程中，目录会在document_tasks中清理
                        
                        strategy_config = self.parsing_strategies.get(file_type, {})
                        logger.info(f"[DOCX] 转换为 PDF 成功，改用 PDF 管线解析: {path_for_parse}")
                        logger.info(f"[DOCX→PDF] PDF文件需要由调用者保存到MinIO，暂不自动清理")
                    else:
                        raise
            
            # 仅使用 Unstructured；任何异常将直接抛出
            logger.info(f"调用 Unstructured.partition，文件={path_for_parse}，配置={strategy_config}")
            
            # ⚠️ 重要：在调用 partition 之前，检查所有可能需要的模型是否已缓存
            # unstructured 库可能加载多个模型：
            # 1. YOLOX 布局检测模型（hi_res 策略）
            # 2. ResNet18 表格结构检测模型（infer_table_structure=True）
            
            # ✅ 关键：确保使用配置的缓存目录，不使用默认位置
            hf_home = settings.HF_HOME or settings.UNSTRUCTURED_MODELS_DIR
            transformers_cache = os.path.join(hf_home, 'transformers_cache')
            hf_hub_cache = os.path.join(hf_home, 'hub')
            
            # ✅ 关键：再次强制设置环境变量，确保 partition 调用时使用配置的目录
            os.environ['HF_HOME'] = hf_home
            os.environ['HF_HUB_CACHE'] = hf_hub_cache
            os.environ['TRANSFORMERS_CACHE'] = transformers_cache
            logger.debug(f"调用 partition 前确认缓存目录: HF_HUB_CACHE={hf_hub_cache}")
            
            def _check_model_in_directory(directory, file_pattern=None, min_size_mb=1):
                """在指定目录中查找模型文件"""
                if not os.path.exists(directory):
                    return False
                try:
                    for root, dirs, files in os.walk(directory):
                        for file in files:
                            file_path = os.path.join(root, file)
                            # 检查文件大小
                            try:
                                file_size = os.path.getsize(file_path)
                                if file_size < min_size_mb * 1024 * 1024:
                                    continue
                                
                                # 如果指定了模式，检查文件名
                                if file_pattern:
                                    if file_pattern(file.lower()):
                                        return True
                                else:
                                    # 默认检查常见模型文件扩展名
                                    if any(file.lower().endswith(ext) for ext in ['.onnx', '.pt', '.pth', '.safetensors', '.bin']):
                                        return True
                            except OSError:
                                continue
                except Exception:
                    pass
                return False
            
            # ✅ 模型检查顺序（严格按照要求）：
            # 1. 首先检查指定路径（settings.py 配置的本地路径）
            # 2. 然后检查配置的缓存目录（settings.py 配置的缓存目录）
            # 3. 如果都没有，准备联网下载到配置的缓存目录
            
            # 1. 检查 YOLOX 模型（仅在 hi_res 策略时）
            yolo_model_path = os.path.join(
                settings.UNSTRUCTURED_MODELS_DIR, 
                'yolo_x_layout', 
                'yolox_10.05.onnx'
            )
            
            yolo_model_exists = False
            yolo_model_path_found = None
            
            # 步骤1：优先检查指定路径（最优先）
            if os.path.exists(yolo_model_path):
                yolo_model_exists = True
                yolo_model_path_found = yolo_model_path
                # ✅ 关键：设置环境变量，强制使用本地模型
                os.environ['UNSTRUCTURED_LAYOUT_MODEL'] = yolo_model_path
                logger.info(f"✅ 步骤1: 在指定路径找到本地 YOLOX 模型: {yolo_model_path}")
            elif strategy_config.get('strategy') == 'hi_res':
                # 步骤2：检查配置的缓存目录
                def _find_yolo_model_in_cache(cache_dir):
                    """在缓存目录中查找 YOLOX 模型"""
                    if not os.path.exists(cache_dir):
                        return None
                    try:
                        for root, dirs, files in os.walk(cache_dir):
                            for file in files:
                                if file.endswith('.onnx') and ('yolo' in file.lower() or 'layout' in file.lower()):
                                    model_path = os.path.join(root, file)
                                    try:
                                        if os.path.getsize(model_path) > 1024 * 1024:  # >1MB
                                            return model_path
                                    except OSError:
                                        continue
                    except Exception:
                        pass
                    return None
                
                # ✅ 只检查配置的缓存目录（settings.py 配置的）
                cached_model = _find_yolo_model_in_cache(transformers_cache)
                if cached_model:
                    yolo_model_exists = True
                    yolo_model_path_found = cached_model
                    # ✅ 关键：设置环境变量，强制使用缓存中的模型
                    os.environ['UNSTRUCTURED_LAYOUT_MODEL'] = cached_model
                    logger.info(f"✅ 步骤2: 在配置的缓存目录中发现 YOLOX 模型: {cached_model}")
                    logger.info(f"✅ 已设置 UNSTRUCTURED_LAYOUT_MODEL 环境变量，强制使用本地缓存，不会访问网络")
                else:
                    # 步骤3：模型不存在，准备下载到配置的缓存目录
                    logger.info(f"⚠️ 步骤3: 模型未在配置的位置找到:")
                    logger.info(f"   指定路径: {yolo_model_path}")
                    logger.info(f"   配置缓存目录: {transformers_cache}")
                    logger.info(f"   准备联网下载到配置的缓存目录")
            
            # ✅ 关键：如果找到了模型，设置离线模式，避免网络请求
            if yolo_model_exists and yolo_model_path_found:
                # ⚠️ 强制设置多个环境变量，确保不访问网络
                os.environ['HF_HUB_OFFLINE'] = '1'  # 强制覆盖，不使用 setdefault
                os.environ['TRANSFORMERS_OFFLINE'] = '1'  # transformers 库的离线模式
                os.environ['HF_DATASETS_OFFLINE'] = '1'  # datasets 库的离线模式
                
                # ✅ 关键：确认 UNSTRUCTURED_LAYOUT_MODEL 已设置
                if 'UNSTRUCTURED_LAYOUT_MODEL' not in os.environ:
                    os.environ['UNSTRUCTURED_LAYOUT_MODEL'] = yolo_model_path_found
                
                logger.info(f"✅ 已强制设置离线模式: HF_HUB_OFFLINE=1, UNSTRUCTURED_LAYOUT_MODEL={yolo_model_path_found}")
                logger.debug(f"环境变量验证: HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE')}, "
                           f"UNSTRUCTURED_LAYOUT_MODEL={os.environ.get('UNSTRUCTURED_LAYOUT_MODEL')}")
            
            # 2. 检查 ResNet18 表格结构检测模型（如果启用了表格结构检测）
            resnet_model_exists = False
            resnet_model_location = None
            if strategy_config.get('infer_table_structure'):
                # ResNet18 模型由 timm 库加载，使用 Hugging Face Hub 的缓存机制
                # timm 使用的模型标识：timm/resnet18.a1_in1k
                # 缓存路径格式：~/.cache/huggingface/hub/models--timm--resnet18.a1_in1k/ 或
                #               transformers_cache/hub/models--timm--resnet18.a1_in1k/
                
                def _check_resnet_model_specific_path(cache_base_dir):
                    """检查 ResNet18 模型的特定缓存路径"""
                    if not os.path.exists(cache_base_dir):
                        return None
                    try:
                        # Hugging Face Hub 的缓存路径格式
                        hub_cache = os.path.join(cache_base_dir, 'hub')
                        if os.path.exists(hub_cache):
                            # 查找 timm/resnet18.a1_in1k 模型的缓存目录
                            # 路径格式：models--timm--resnet18.a1_in1k (空格和斜杠被替换为 --)
                            model_dirs = [
                                'models--timm--resnet18.a1_in1k',
                                'models--timm--resnet18',
                                'models--resnet18',
                            ]
                            for model_dir_name in model_dirs:
                                model_dir = os.path.join(hub_cache, model_dir_name)
                                if os.path.exists(model_dir):
                                    # 检查目录中是否有模型文件
                                    for root, dirs, files in os.walk(model_dir):
                                        for file in files:
                                            if (file.endswith('.safetensors') or 
                                                file.endswith('.bin') or 
                                                file.endswith('.pt') or 
                                                file.endswith('.pth')):
                                                file_path = os.path.join(root, file)
                                                try:
                                                    if os.path.getsize(file_path) > 10 * 1024 * 1024:  # >10MB
                                                        return file_path
                                                except OSError:
                                                    continue
                        # 如果没找到特定的 hub 目录，使用通用的递归查找
                        for root, dirs, files in os.walk(cache_base_dir):
                            for file in files:
                                file_lower = file.lower()
                                # 精确匹配 resnet18 相关文件
                                if (('resnet18' in file_lower or 
                                     ('timm' in file_lower and 'resnet' in file_lower)) and
                                    (file.endswith('.safetensors') or 
                                     file.endswith('.bin') or 
                                     file.endswith('.pt') or 
                                     file.endswith('.pth'))):
                                    file_path = os.path.join(root, file)
                                    try:
                                        if os.path.getsize(file_path) > 10 * 1024 * 1024:  # >10MB
                                            return file_path
                                    except OSError:
                                        continue
                    except Exception:
                        pass
                    return None
                
                # 检查指定缓存目录
                cached_model = _check_resnet_model_specific_path(transformers_cache)
                if cached_model:
                    resnet_model_exists = True
                    resnet_model_location = cached_model
                    logger.info(f"✅ 在指定缓存目录中发现 ResNet18 表格结构检测模型: {cached_model}")
                    logger.info(f"💡 timm 库将自动使用缓存中的模型（日志中可能仍显示 'Loading from Hugging Face hub'，但实际是从缓存加载）")
                # ⚠️ 不再检查默认缓存目录 ~/.cache/huggingface
                # 所有模型都应该在配置的缓存目录中（HF_HOME 或 UNSTRUCTURED_MODELS_DIR）
                logger.debug(f"ResNet18 模型未在配置的缓存目录中找到，将仅在配置目录中查找或下载")
            
            # 判断是否需要下载 YOLOX 模型
            need_yolo_download = (
                strategy_config.get('strategy') == 'hi_res' and 
                not yolo_model_exists and 
                settings.UNSTRUCTURED_AUTO_DOWNLOAD_MODEL
            )
            
            if need_yolo_download:
                # 记录下载开始（仅在确实需要使用 hi_res 且本地/缓存中都不存在时）
                log_download_start(
                    model_name="YOLOX 布局检测模型",
                    source="Hugging Face",
                    estimated_size="10-50 MB"
                )
                logger.info(f"💾 模型将下载到缓存目录: {transformers_cache}")
            
            # ResNet18 表格结构检测模型的下载判断
            need_resnet_download = (
                strategy_config.get('infer_table_structure') and 
                not resnet_model_exists and 
                settings.UNSTRUCTURED_AUTO_DOWNLOAD_MODEL
            )
            
            if need_resnet_download:
                # 记录下载开始（仅在确实需要表格结构检测且缓存中不存在时）
                log_download_start(
                    model_name="ResNet18 表格结构检测模型",
                    source="Hugging Face",
                    estimated_size="50-100 MB"
                )
                logger.info(f"💾 模型将下载到缓存目录: {transformers_cache}")
                logger.info(f"📝 注意：timm 库加载时日志可能显示 'Loading from Hugging Face hub'，这是正常的日志输出")
            elif strategy_config.get('infer_table_structure') and resnet_model_exists:
                # 明确告知缓存存在，将使用缓存
                logger.info(f"✅ ResNet18 表格结构检测模型已在缓存中: {resnet_model_location}")
                logger.info(f"💡 将直接使用缓存中的模型，无需下载（timm 库的日志可能仍显示 'Loading from Hugging Face hub'，但实际是从缓存加载）")
            
            try:
                # ✅ 关键：在调用 partition 之前，最后一次强制设置环境变量
                # 根据模型是否存在，设置不同的策略：
                # 1. 如果模型存在：设置离线模式，强制使用本地模型
                # 2. 如果模型不存在：确保下载到配置的缓存目录
                
                if yolo_model_exists and yolo_model_path_found:
                    # ✅ 策略1：模型已存在，设置离线模式，强制使用本地模型
                    os.environ['HF_HUB_OFFLINE'] = '1'
                    os.environ['TRANSFORMERS_OFFLINE'] = '1'
                    os.environ['HF_DATASETS_OFFLINE'] = '1'
                    os.environ['UNSTRUCTURED_LAYOUT_MODEL'] = yolo_model_path_found
                    
                    logger.info(f"✅ 模型已存在，设置离线模式，强制使用本地模型:")
                    logger.info(f"   UNSTRUCTURED_LAYOUT_MODEL={yolo_model_path_found}")
                    logger.info(f"   HF_HUB_OFFLINE=1（禁用网络请求）")
                else:
                    # ✅ 策略2：模型不存在，需要下载，确保下载到配置的缓存目录
                    # 移除离线模式，允许下载
                    if 'HF_HUB_OFFLINE' in os.environ:
                        del os.environ['HF_HUB_OFFLINE']
                    if 'TRANSFORMERS_OFFLINE' in os.environ:
                        del os.environ['TRANSFORMERS_OFFLINE']
                    if 'HF_DATASETS_OFFLINE' in os.environ:
                        del os.environ['HF_DATASETS_OFFLINE']
                    
                    # ✅ 关键：确保下载到配置的缓存目录
                    # huggingface_hub 会使用 HF_HUB_CACHE 环境变量指定的目录
                    os.environ['HF_HUB_CACHE'] = hf_hub_cache
                    os.environ['HF_HOME'] = hf_home
                    os.environ['TRANSFORMERS_CACHE'] = transformers_cache
                    
                    logger.info(f"📥 模型不存在，准备下载到配置的缓存目录:")
                    logger.info(f"   HF_HUB_CACHE={hf_hub_cache}")
                    logger.info(f"   HF_HOME={hf_home}")
                    logger.info(f"   TRANSFORMERS_CACHE={transformers_cache}")
                
                # ⚠️ 尝试 monkey patch huggingface_hub，确保下载到配置目录（如果模型不存在）
                if not yolo_model_exists or not yolo_model_path_found:
                    try:
                        import huggingface_hub.file_download
                        original_hf_hub_download = getattr(huggingface_hub.file_download, 'hf_hub_download', None)
                        
                        if original_hf_hub_download:
                            def patched_hf_hub_download(*args, **kwargs):
                                """确保模型下载到配置的缓存目录"""
                                # ✅ 强制使用配置的缓存目录
                                # 注意：不要在 kwargs 中重复设置 cache_dir，避免 "multiple values" 错误
                                if 'cache_dir' not in kwargs:
                                    kwargs['cache_dir'] = hf_hub_cache
                                else:
                                    # 如果已经指定了 cache_dir，使用配置的目录覆盖
                                    kwargs['cache_dir'] = hf_hub_cache
                                
                                repo_id = args[0] if len(args) > 0 else kwargs.get('repo_id', 'unknown')
                                filename = args[1] if len(args) > 1 else kwargs.get('filename', 'unknown')
                                
                                logger.debug(f"下载模型 {repo_id}/{filename} 到配置目录: {hf_hub_cache}")
                                try:
                                    return original_hf_hub_download(*args, **kwargs)
                                except Exception as e:
                                    logger.warning(f"从配置目录下载失败，尝试使用原始函数: {e}")
                                    # 移除 cache_dir 参数，让原始函数使用默认行为
                                    kwargs.pop('cache_dir', None)
                                    return original_hf_hub_download(*args, **kwargs)
                            
                            # ✅ 启用 monkey patch，确保下载到配置目录
                            huggingface_hub.file_download.hf_hub_download = patched_hf_hub_download
                            logger.debug(f"✅ 已启用 huggingface_hub monkey patch，确保下载到配置目录")
                    except Exception as e:
                        logger.debug(f"准备 monkey patch huggingface_hub 时出错（不影响下载）: {e}")
                
                elements = partition(filename=path_for_parse, **strategy_config)
                logger.info(f"Unstructured解析完成，提取到 {len(elements)} 个元素")
                
                # 如果确实进行了 YOLOX 下载，记录成功
                if need_yolo_download:
                    log_download_success(
                        model_name="YOLOX 布局检测模型",
                        save_path=transformers_cache
                    )
                
                # 如果确实进行了 ResNet18 下载，记录成功
                if need_resnet_download:
                    log_download_success(
                        model_name="ResNet18 表格结构检测模型",
                        save_path=transformers_cache
                    )
                    
            except Exception as parse_error:
                # 判断是否是模型下载相关的错误
                error_str = str(parse_error).lower()
                is_download_error = any(keyword in error_str for keyword in [
                    'download', 'huggingface', 'hub', 'network', 'connection', 
                    'timeout', 'unpack', 'http', 'https', 'ssl', 'certificate',
                    'yolo', 'layout', 'model', 'resnet', 'timm', 'table'
                ])
                
                if is_download_error:
                    log_download_error(
                        model_name="YOLOX 布局检测模型",
                        error=parse_error,
                        download_url="https://huggingface.co/unstructuredio/yolo_x_layout/resolve/main/yolox_10.05.onnx",
                        local_path=yolo_model_path,
                        readme_path="models/unstructured/README.md"
                    )
                    
                    raise CustomException(
                        code=ErrorCode.DOCUMENT_PARSING_FAILED,
                        message=f"YOLOX模型下载失败: {str(parse_error)}。请检查网络连接或手动下载模型到 {yolo_model_path}。详见 models/unstructured/README.md"
                    )
                else:
                    # 其他解析错误，直接抛出
                    raise
            
            # 确定实际解析的文件类型（可能是转换后的PDF）
            # 如果Word文档被转换为PDF，应该按PDF处理（应用PDF特有的OCR噪声过滤）
            actual_file_type = os.path.splitext(path_for_parse)[1].lower()
            is_actually_pdf = actual_file_type == '.pdf'
            
            # 处理解析结果（使用原始文件路径和大小，但传递实际文件类型信息）
            result = self._process_parsed_elements(elements, original_file_path, file_size, is_pdf=is_actually_pdf)
            
            # 如果转换了PDF，记录PDF路径（调用者需要保存到MinIO）
            # 注意：转换后的PDF不在finally中清理，需要调用者保存后再清理
            converted_pdf_path_in_result = None
            if path_for_parse != original_file_path and actual_file_type == '.pdf':
                converted_pdf_path_in_result = path_for_parse
                result['converted_pdf_path'] = path_for_parse  # 临时PDF路径
                result['is_converted_pdf'] = True  # 标记是转换后的PDF
                logger.info(f"[DOCX→PDF] 已转换PDF，临时路径: {path_for_parse}，需要保存到MinIO后再清理")
                logger.info(f"[DOCX→PDF] 已应用PDF特有的OCR噪声过滤策略")
                
                # 从清理列表中移除PDF文件（调用者负责清理）
                if path_for_parse in temp_files_to_cleanup:
                    temp_files_to_cleanup.remove(path_for_parse)
                    logger.debug(f"[DOCX→PDF] 已将PDF从自动清理列表中移除: {path_for_parse}")
            
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
        finally:
            # 清理所有临时文件（无论成功还是失败都要清理）
            self._cleanup_temp_files(temp_files_to_cleanup, temp_dirs_to_cleanup)
    
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
    
    def _is_table_of_contents(self, element_text: str, element_category: str, coordinates: Dict[str, Any], page_number: int) -> bool:
        """
        判断元素是否是目录
        
        目录特征：
        1. 包含章节编号模式（如 1.1, 1.2.1, 2.3.4 等）
        2. 包含页码数字（通常在行尾）
        3. 可能包含"目录"、"Table of Contents"等关键词
        4. 可能包含连接点（... 或多个空格分隔）
        5. 表格类型但内容是目录结构
        """
        if not element_text or len(element_text.strip()) < 5:
            return False
        
        # 检查是否包含目录关键词
        toc_keywords = [
            r'目录', r'目\s*录', r'Table\s+of\s+Contents', r'CONTENTS',
            r'分块内容', r'章节目录', r'内容目录'  # 移除太宽泛的"内容"、"章节"
        ]
        has_toc_keyword = any(re.search(keyword, element_text, re.IGNORECASE) for keyword in toc_keywords)
        
        # 检查章节编号模式（如 1.1, 1.2.1, 2.3.4.5）
        # 支持多种格式：1.1、1.1.1、I.1、一、1.2.3.4 等
        section_patterns = [
            r'\d+\.\d+(?:\.\d+)*',  # 1.1, 1.2.3, 1.2.3.4
            r'[一二三四五六七八九十]+[\.、]',  # 一、二、三、
            r'[IVX]+\.\d+',  # I.1, II.2.3
            r'第[一二三四五六七八九十\d]+[章节条]',  # 第一章、第二节
        ]
        has_section_number = any(re.search(pattern, element_text) for pattern in section_patterns)
        
        # 检查是否包含页码（数字在行尾，可能被点分隔）
        # 页码通常在行末，可能前后有空格或点
        page_number_patterns = [
            r'\d+\s*$',  # 行尾数字
            r'\.\.\.+\s*\d+',  # ... 123
            r'\s+\d+\s*$',  # 多个空格后跟数字在行尾
        ]
        has_page_number = any(re.search(pattern, element_text, re.MULTILINE) for pattern in page_number_patterns)
        
        # 检查连接点模式（目录常用 ... 或空格分隔标题和页码）
        has_leader_dots = '...' in element_text or '…' in element_text
        
        # 如果是Table类型，但内容符合目录特征，很可能是误识别
        if element_category == 'Table':
            # 表格被识别为目录的条件更严格
            if has_toc_keyword and (has_section_number or has_page_number):
                return True
            if has_section_number and has_page_number and has_leader_dots:
                return True
            # 检查表格单元格是否呈现目录结构（多数行包含章节号+页码）
            lines = element_text.split('\n')
            section_lines = 0
            lines_to_check = lines[:10]  # 只检查前10行
            if len(lines_to_check) > 0:
                for line in lines_to_check:
                    if any(re.search(pattern, line) for pattern in section_patterns):
                        if any(re.search(pattern, line) for pattern in page_number_patterns):
                            section_lines += 1
                if section_lines / len(lines_to_check) > 0.5:  # 超过50%的行符合目录模式
                    return True
        
        # 对于文本类型，条件稍微宽松
        if element_category not in ['Table', 'Image']:
            if has_toc_keyword:
                return True
            if has_section_number and has_page_number:
                return True
            if has_section_number and has_leader_dots:
                return True
        
        return False
    
    def _is_header_or_footer(self, element_text: str, element_category: str, coordinates: Dict[str, Any], page_number: int, page_height: float = 0) -> bool:
        """
        判断元素是否是页眉或页脚
        
        页眉页脚特征：
        1. 位置在页面顶部或底部（根据坐标判断）- ⚠️ 优先使用坐标判断
        2. 通常包含页码、文档标题、日期等
        3. 可能每页重复出现
        4. 文本通常较短
        5. 可能包含页眉页脚关键词（作为补充判断）
        
        判断策略（优先级）：
        1. 优先使用坐标位置判断（最准确）
        2. 如果坐标信息不可用，使用内容特征判断（关键词、长度等）
        """
        if not element_text:
            return False
        
        text_stripped = element_text.strip()
        
        # ⚠️ 策略1：优先使用坐标位置判断（最准确可靠）
        if coordinates and page_height > 0:
            y_pos = coordinates.get('y', 0)
            element_height = coordinates.get('height', 0)
            element_bottom = y_pos + element_height
            
            # ✅ 优化：更严格的页眉页脚区域判断
            # 页眉：在页面顶部15%以内（更严格，避免误判正文标题）
            # 页脚：在页面底部15%以内（更严格，避免误判正文）
            # 同时考虑元素本身的高度，如果元素很高（占页面超过50%），不应被判断为页眉页脚
            element_height_ratio = element_height / page_height if page_height > 0 else 0
            
            # 只有当元素高度不超过页面的50%时，才进行页眉页脚判断
            if element_height_ratio <= 0.5:
                is_in_header_zone = y_pos < page_height * 0.15  # 从20%调整为15%，更严格
                is_in_footer_zone = element_bottom > page_height * 0.85  # 从80%调整为85%，更严格
            else:
                # 元素太高，不可能是页眉页脚
                is_in_header_zone = False
                is_in_footer_zone = False
            
            if is_in_header_zone or is_in_footer_zone:
                # 位置符合页眉页脚区域，进一步验证内容特征
                text_len = len(text_stripped)
                
                # ✅ 优化：更严格的页眉页脚判断
                # 页眉页脚通常文本较短，且位置在页面边缘
                # 对于位置在页眉页脚区域的元素，需要同时满足位置和内容特征
                
                # 1. 如果文本很短（<50字符），位置又符合，很可能是页眉页脚
                if text_len < 50:
                    # 对于非常短的文本（<30字符），位置符合就认为是页眉页脚
                    if text_len < 30:
                        return True
                    
                    # 对于稍长的文本（30-50字符），需要额外验证内容特征
                    # 检查是否包含典型的页眉页脚内容
                    # 页码格式
                    page_number_patterns = [
                        r'^页\s*\d+', r'^第\s*\d+\s*页', r'^Page\s+\d+', r'^PAGE\s+\d+',
                        r'^共\s*\d+\s*页', r'^\d+/\d+$',  # "1/10"格式
                        r'^\s*\d+\s*$',  # 纯页码数字
                    ]
                    if any(re.search(pattern, text_stripped, re.IGNORECASE) for pattern in page_number_patterns):
                        return True
                    
                    # 日期格式
                    date_pattern = r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?'
                    if re.search(date_pattern, text_stripped):
                        return True
                    
                    # 保密声明、内部资料（通常在页眉页脚）
                    header_footer_content_patterns = [
                        r'内部资料', r'请勿外传', r'禁止外传', r'保密', r'机密',
                        r'仅供.*使用', r'不得.*传播',
                        # 公司名称单独出现（通常是页眉页脚）
                        r'^[\w\s（）()\-]+有限公司$',
                        r'^[\w\s（）()\-]+股份有限公司$',
                        r'^[\w\s（）()\-]+集团$',
                        r'^[\w\s（）()\-]+公司$',
                    ]
                    if any(re.search(pattern, text_stripped, re.IGNORECASE) for pattern in header_footer_content_patterns):
                        return True
                    
                    # 公司名称 + 保密声明组合
                    company_secret_patterns = [
                        r'[\w\s（）()\-]+有限公司.*内部资料',
                        r'[\w\s（）()\-]+有限公司.*请勿外传',
                        r'内部资料.*[\w\s（）()\-]+有限公司',
                        r'请勿外传.*[\w\s（）()\-]+有限公司',
                    ]
                    if any(re.search(pattern, text_stripped, re.IGNORECASE) for pattern in company_secret_patterns):
                        return True
                else:
                    # 文本较长（>=50字符），即使位置符合，也很可能是正文（如小标题）
                    return False
        
        # ⚠️ 策略2：如果没有坐标信息，使用内容特征判断（作为后备方案）
        # 注意：这种方式可能误判，但比完全不判断要好
        
        # 检查典型的页眉页脚关键词和内容模式
        header_footer_keywords = [
            r'^页\s*\d+', r'^第\s*\d+\s*页', r'^Page\s+\d+', r'^PAGE\s+\d+',
            r'^共\s*\d+\s*页', r'^\d+/\d+$',  # 页码格式如 "1/10"
        ]
        
        # 检查是否是典型的页眉页脚内容（保密声明、公司名称等）
        header_footer_content_patterns = [
            # 保密声明、内部资料
            r'内部资料', r'请勿外传', r'禁止外传', r'保密', r'机密',
            r'仅供.*使用', r'不得.*传播',
            # 公司名称单独出现（通常是页眉页脚）
            r'^[\w\s（）()\-]+有限公司$',  # 纯公司名称，如 "XX有限公司"
            r'^[\w\s（）()\-]+股份有限公司$',
            r'^[\w\s（）()\-]+集团$',
            r'^[\w\s（）()\-]+公司$',
            # 公司名称 + 保密声明组合
            r'[\w\s（）()\-]+有限公司.*内部资料',
            r'[\w\s（）()\-]+有限公司.*请勿外传',
            r'内部资料.*[\w\s（）()\-]+有限公司',
            r'请勿外传.*[\w\s（）()\-]+有限公司',
        ]
        
        # 如果匹配页眉页脚内容模式，且文本较短，可能是页眉页脚
        if len(text_stripped) < 60:  # 页眉页脚通常较短
            if any(re.search(pattern, text_stripped, re.IGNORECASE) for pattern in header_footer_content_patterns):
                return True
            
            # 如果文本很短（少于30字符）且匹配页眉页脚关键词模式
            if len(text_stripped) < 30:
                if any(re.search(keyword, text_stripped, re.IGNORECASE) for keyword in header_footer_keywords):
                    return True
                # 纯数字（可能是页码）
                if re.match(r'^\d+$', text_stripped):
                    # 排除明显不是页码的长数字
                    if len(text_stripped) <= 4:  # 页码通常不超过4位
                        return True
        
        # 如果内容只包含日期、页码等简短信息
        if len(text_stripped) < 20:
            date_pattern = r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?'
            if re.search(date_pattern, text_stripped):
                return True
        
        return False
    
    def _is_blank_content(self, element_text: str) -> bool:
        """
        判断元素是否是空白内容
        
        空白内容特征：
        1. 文本为空或仅包含空白字符
        2. 文本长度过短（< 3个字符）且无实际意义
        3. 仅包含标点符号、特殊字符
        """
        if not element_text:
            return True
        
        text_stripped = element_text.strip()
        
        # 完全空白
        if not text_stripped:
            return True
        
        # 仅包含空白字符、换行符、制表符等
        if not _RE_CHARS_ONLY.search(text_stripped):
            return True
        
        # 过短且无实际意义的文本（可能是OCR噪声）
        if len(text_stripped) < 3:
            # 如果是单字符且不是常见有意义字符，视为噪声
            if len(text_stripped) == 1 and text_stripped not in ['。', '，', '！', '？', '；', '：', '.', ',', '!', '?']:
                return True
        
        # 仅包含数字和标点（可能是条形码、编号等）
        if len(text_stripped) < 10:
            if re.match(r'^[\d\s\-_./\\]+$', text_stripped):
                return True
        
        return False
    
    def _is_copyright_page(self, element_text: str, page_number: int, total_pages: int = 0, coordinates: Dict[str, Any] = None) -> bool:
        """
        判断元素是否是版权声明页
        
        版权声明特征：
        1. 包含版权关键词
        2. 通常在文档末尾（后10%的页面）- ⚠️ 优先使用页码和坐标判断
        3. 可能包含版权符号、年份、出版社信息
        4. 位置通常在页面底部区域
        
        判断策略（优先级）：
        1. 优先使用页码位置判断（在文档末尾）
        2. 结合坐标位置判断（在页面底部）
        3. 如果位置信息不可用，使用内容特征判断（关键词）
        """
        if not element_text or len(element_text.strip()) < 20:
            return False
        
        text_lower = element_text.lower()
        text_stripped = element_text.strip()
        
        # ⚠️ 策略1：优先使用页码位置判断
        # 版权声明通常在文档末尾（后10%的页面）
        is_in_last_pages = False
        if total_pages > 0:
            page_ratio = page_number / total_pages if total_pages > 0 else 0
            # 如果页码在文档的后10%，很可能是版权页
            is_in_last_pages = page_ratio > 0.90
        
        # ⚠️ 策略2：结合坐标位置判断（如果可用）
        # 版权声明通常在页面底部区域
        # 注意：copyright_page 的判断主要依赖页码，坐标作为辅助
        
        # 版权相关关键词
        copyright_keywords = [
            r'版权', r'copyright', r'©', r'\(c\)', r'all rights reserved',
            r'版权所有', r'版权所有\s*©', r'published by', r'出版社',
            r'isbn', r'issn', r'印刷', r'出版', r'印次',
            r'未经许可', r'禁止', r'不得', r'法律保护'
        ]
        
        has_copyright_keyword = any(re.search(keyword, text_lower, re.IGNORECASE) for keyword in copyright_keywords)
        
        # 如果位置符合（在文档末尾）且包含版权关键词，很可能是版权声明
        if is_in_last_pages and has_copyright_keyword:
            if len(text_stripped) < 500:  # 版权页通常内容简洁
                return True
        
        # 如果包含版权关键词且文本较短（版权页通常内容简洁）
        # 即使不在文档末尾，也可能是版权声明片段
        if has_copyright_keyword and len(text_stripped) < 500:
            # 检查是否包含版权年份模式（如 © 2024, Copyright 2024）
            copyright_year_pattern = r'(?:copyright|©|\(c\))\s*(?:©|\()?\s*\d{4}'
            if re.search(copyright_year_pattern, text_lower):
                return True
            # 如果文本很短（<100字符），即使没有年份也可能是版权片段
            if len(text_stripped) < 100:
                return True
        
        return False
    
    def _is_valid_content(self, element_text: str) -> bool:
        """
        通用内容保护函数：判断文本是否是有效的文档内容
        
        这个函数用于在所有降噪过滤器之前，识别并保护正常的内容，
        防止误判。适用于所有类型的文档。
        
        保护的内容类型：
        1. 包含章节编号的标题（单数字、多级、中文、罗马数字等）
        2. 技术内容（函数调用、端口号、URL、JSON、代码、配置等）
        3. 结构化内容（列表项、表格内容、公式、命令等）
        4. 较长的有意义文本段落（中文>=5字符，英文>=10字符）
        
        ⚠️ 注意：即使满足以上条件，如果内容是典型的页眉页脚、水印、版权声明等，
        也不应该被保护（应该在降噪过滤阶段被移除）。
        
        参数:
            element_text: 要检查的文本
            
        返回:
            True 如果是有效的文档内容（应该被保护，不应被过滤）
        """
        if not element_text:
            return False
        
        text_stripped = element_text.strip()
        if not text_stripped:
            return False
        
        # ⚠️ 重要：先检查是否是典型的页眉页脚、水印、版权声明等内容
        # 即使这些内容满足其他"有效内容"条件（如长度、中文字符等），也不应该被保护
        header_footer_watermark_patterns = [
            # 保密声明、内部资料
            r'内部资料', r'请勿外传', r'禁止外传', r'保密', r'机密',
            r'内部', r'外部', r'仅供.*使用', r'不得.*传播',
            # 版权声明
            r'版权所有', r'Copyright', r'©', r'®',
            r'保留.*权利', r'All rights reserved',
            # 水印关键词
            r'水印', r'Watermark', r'样本', r'Sample', r'草案', r'Draft',
            # 公司名称单独出现（通常是页眉页脚）
            r'^[\w\s（）()]{5,50}有限公司$',  # 纯公司名称
            r'^[\w\s（）()]{5,50}股份有限公司$',
            r'^[\w\s（）()]{5,50}集团$',
            # 典型的页眉页脚短语组合
            r'内部资料.*请勿外传', r'请勿外传.*内部资料',
            r'保密.*不得.*传播', r'不得.*传播.*保密',
        ]
        # 检查是否匹配页眉页脚/水印/版权声明模式
        if any(re.search(pattern, text_stripped, re.IGNORECASE) for pattern in header_footer_watermark_patterns):
            # 如果是典型的页眉页脚内容，即使满足其他条件也不保护
            return False
        
        # 1. 检查是否包含章节编号（各种格式）- 使用预编译的正则表达式提升性能
        if (_RE_SECTION_SINGLE.search(text_stripped) or
            _RE_SECTION_MULTI.search(text_stripped) or
            _RE_SECTION_CHINESE.search(text_stripped) or
            _RE_SECTION_ROMAN.search(text_stripped) or
            _RE_SECTION_CHAPTER.search(text_stripped) or
            _RE_SECTION_PART.search(text_stripped) or
            _RE_APPENDIX_EN.search(text_stripped) or
            _RE_APPENDIX_CN.search(text_stripped)):
            return True
        
        # 2. 检查是否包含技术内容（各种格式）
        technical_patterns = [
            # 函数调用和方法调用
            r'[a-zA-Z0-9_\-\.]+\s*\(',  # function(), method(), obj.method()
            r'[a-zA-Z0-9_\-]+\s*=\s*[a-zA-Z0-9_\-]+\s*\(',  # var = func()
            
            # 端口号和网络地址
            r':\s*\d{1,5}(?:/\w+)?',  # :27017, :8080/path
            r'[a-zA-Z0-9\-\.]+:\d+',  # host:port
            
            # URL和域名
            r'https?://[\w\.\-]+',  # http://, https://
            r'[\w\.\-]+\.[\w\.\-]+\.\w+',  # domain.com, sub.domain.org
            r'ftp://[\w\.\-]+',  # ftp://
            
            # JSON对象和数组
            r'\{[\s\S]*\}',  # { ... }
            r'\[[\s\S]*\]',  # [ ... ]
            
            # 代码块特征
            r'```[\s\S]*```',  # ```code```
            r'<code>[\s\S]*</code>',  # <code>...</code>
            r'#\s*\w+',  # # comment (shell/python)
            r'//\s*\w+',  # // comment
            r'/\*[\s\S]*\*/',  # /* comment */
            
            # 命令行和脚本
            r'^\$\s+',  # $ command
            r'^>\s+',  # > prompt
            r'^C:\\',  # C:\path (Windows)
            r'^/\w+',  # /path (Unix)
            r'^\w+://',  # protocol://
            
            # 配置文件格式
            r'^\s*\w+\s*[:=]\s*\w+',  # key: value, key=value
            r'<[\w/]+>',  # XML tags
            r'&[\w]+;',  # XML entities
        ]
        if any(re.search(pattern, text_stripped, re.IGNORECASE | re.MULTILINE) for pattern in technical_patterns):
            return True
        
        # 3. 检查结构化内容
        structured_patterns = [
            # 列表项（各种标记）
            r'^[\-•·▪▫◦‣⁃]\s+',  # - item, • item
            r'^\d+[\.\)]\s+',  # 1. item, 1) item
            r'^[a-zA-Z][\.\)]\s+',  # a. item, a) item
            r'^[IVX]+[\.\)]\s+',  # I. item, I) item
            r'^[一二三四五六七八九十]+[\.、]\s+',  # 一、item
            
            # 表格内容特征
            r'\|\s*.+\s*\|',  # | cell | cell |
            r'\s+\|\s+',  # spaces | spaces
            
            # 公式和表达式
            r'[a-zA-Z]\s*[+\-*/=]\s*[a-zA-Z0-9]',  # x = y + z
            r'[a-zA-Z0-9]+\s*[<>≤≥=]\s*[a-zA-Z0-9]+',  # x >= y
            r'\$\$?[\s\S]*\$\$?',  # $formula$ (LaTeX)
            
            # 引用格式
            r'^>\s+',  # > quote
            r'^"[\s\S]*"$',  # "quoted text"
            r'^「[\s\S]*」$',  # 「quoted text」
        ]
        if any(re.search(pattern, text_stripped, re.MULTILINE) for pattern in structured_patterns):
            return True
        
        # 4. 检查较长的有意义文本段落
        # 中文：>=5个连续汉字（有意义的中文段落）- 使用预编译正则
        if _RE_CHINESE_5_CHARS.search(text_stripped):
            return True
        
        # 英文：>=10个字母（有意义的英文段落）
        # 排除纯数字、纯符号等 - 使用预编译正则
        english_words = _RE_ENGLISH_WORD.findall(text_stripped)
        if len(english_words) >= 3:  # 至少3个单词
            return True
        
        # 中英文混合：包含中文字符且总长度>=10
        if _RE_CHINESE.search(text_stripped) and len(text_stripped) >= 10:
            return True
        
        # 5. 检查是否包含有意义的标点和格式
        # 如果包含多种标点（句号、问号、感叹号等），可能是完整句子
        sentence_endings = ['.', '。', '!', '！', '?', '？', ';', '；']
        if sum(1 for char in text_stripped if char in sentence_endings) >= 1:
            # 且文本长度>=8，可能是完整句子
            if len(text_stripped) >= 8:
                return True
        
        return False
    
    def _is_noise_text(self, element_text: str, is_pdf: bool = False) -> bool:
        """
        判断文本是否是噪声（OCR错误、碎片文本等）
        
        噪声特征：
        1. 过短的文本片段（< 5个字符，且无意义）
        2. 仅包含特殊字符
        3. 重复字符过多（如 "aaabbbccc"）
        4. 字符比例异常（如全是标点）
        5. PDF OCR常见错误模式（如果is_pdf=True）
        
        注意：包含章节编号的文本（如"1.1.标题"）不应被识别为噪声
        
        参数:
            element_text: 要检查的文本
            is_pdf: 是否为PDF文件（PDF的OCR错误更多，需要更严格的过滤）
        """
        if not element_text:
            return True
        
        text_stripped = element_text.strip()
        
        # ⚠️ 重要：检查是否包含章节编号模式（如 1.1, 1.2.1, 第一章 等）
        # 包含章节编号的文本通常是标题或目录项，不应被识别为噪声
        section_patterns = [
            r'^\d+\.',  # 单数字加点开头，如 1.、4. 等
            r'\d+\.\d+(?:\.\d+)*',  # 1.1, 1.2.3, 1.2.3.4
            r'[一二三四五六七八九十]+[\.、]',  # 一、二、三、
            r'[IVX]+\.\d+',  # I.1, II.2.3
            r'第[一二三四五六七八九十\d]+[章节条]',  # 第一章、第二节
        ]
        has_section_number = any(re.search(pattern, text_stripped) for pattern in section_patterns)
        
        # 如果包含章节编号，即使是短文本也认为是有效内容（标题）
        if has_section_number:
            return False
        
        # PDF OCR错误：检查常见OCR误识别模式
        if is_pdf:
            # 1. 检查是否有大量相似字符混合（OCR常见错误）
            # 例如：l1|I、O0、rn m等易混淆字符
            confusing_chars = ['l', '1', '|', 'I', 'O', '0']
            confusing_count = sum(text_stripped.count(char) for char in confusing_chars)
            if len(text_stripped) > 0 and confusing_count / len(text_stripped) > 0.5:
                # 如果混淆字符占比过高，可能是OCR错误
                return True
            
            # 2. 检查是否有大量随机字符组合（OCR噪声）
            # 连续出现的非单词字符组合（使用预编译的正则表达式）
            if len(text_stripped) > 10:  # 只对较长文本检查
                random_matches = len(_RE_RANDOM_CHARS.findall(text_stripped))
                if random_matches > 0 and random_matches / len(text_stripped) > 0.3:
                    return True
        
        # 过短文本（可能是OCR碎片）
        # PDF OCR错误产生的碎片可能更短，所以对PDF使用更严格的阈值
        min_length = MIN_TEXT_LENGTH_FOR_NOISE_PDF if is_pdf else MIN_TEXT_LENGTH_FOR_NOISE
        if len(text_stripped) < min_length:
            # 检查是否是有意义的短文本（如"是"、"否"、"OK"等）
            meaningful_short = ['是', '否', 'ok', 'no', 'yes', 'true', 'false', 'a', 'i']
            if text_stripped.lower() not in meaningful_short:
                return True
        
        # 仅包含特殊字符
        if not _RE_CHARS_ONLY.search(text_stripped):
            return True
        
        # 字符比例异常：如果标点符号占比过高（PDF使用更严格阈值）
        punctuation_threshold = 0.6 if is_pdf else 0.7
        punctuation_count = len(_RE_PUNCTUATION.findall(text_stripped))
        if len(text_stripped) > 0 and punctuation_count / len(text_stripped) > punctuation_threshold:
            return True
        
        # 重复字符过多（如 "aaa"、"---"）
        if len(text_stripped) >= 3:
            # 检查是否有超过80%的字符相同
            char_counts = {}
            for char in text_stripped:
                char_counts[char] = char_counts.get(char, 0) + 1
            max_char_count = max(char_counts.values()) if char_counts else 0
            if max_char_count / len(text_stripped) > 0.8:
                return True
        
        # PDF特殊：检查是否有大量单个字符被空格分隔（OCR错误模式）
        if is_pdf and len(text_stripped.split()) > 3:
            single_char_words = len([w for w in text_stripped.split() if len(w) == 1])
            total_words = len(text_stripped.split())
            if single_char_words / total_words > 0.5:
                return True
        
        return False
    
    def _is_watermark(self, element_text: str, coordinates: Dict[str, Any], page_number: int, page_height: float = 0, page_width: float = 0) -> bool:
        """
        判断元素是否是水印文字
        
        水印特征：
        1. 文本通常较短且重复（如"保密"、"CONFIDENTIAL"、"DRAFT"等）
        2. 位置可能在页面中央或角落（⚠️ 优先使用坐标判断）
        3. 可能倾斜、半透明（OCR识别可能不完整）
        4. 字体大小可能异常
        
        判断策略（优先级）：
        1. 优先使用坐标位置判断（最准确）
        2. 如果坐标信息不可用，使用内容特征判断（关键词、重复模式等）
        
        注意：正常段落中如果包含水印关键词（如"内部资料"），不应被识别为水印
        """
        if not element_text:
            return False
        
        import re
        
        text_stripped = element_text.strip()
        text_upper = text_stripped.upper()
        text_original = element_text.strip()  # 保留原始文本用于检查章节编号
        
        # ⚠️ 重要：检查是否包含章节编号或是有意义的段落
        # 如果文本包含章节编号、技术内容（如配置、命令等），不应被识别为水印
        section_patterns = [
            r'^\d+\.',  # 单数字加点开头，如 1.、4. 等
            r'\d+\.\d+(?:\.\d+)*',  # 1.1, 1.2.3, 1.2.3.4
            r'[一二三四五六七八九十]+[\.、]',  # 一、二、三、
            r'[IVX]+\.\d+',  # I.1, II.2.3
            r'第[一二三四五六七八九十\d]+[章节条]',  # 第一章、第二节
        ]
        has_section_number = any(re.search(pattern, text_original) for pattern in section_patterns)
        
        # 检查是否包含技术内容（如配置、命令、URL等）
        has_technical_content = bool(
            re.search(r'[a-zA-Z0-9_\-\.]+\(', text_original) or  # 函数调用如 rs.conf()
            re.search(r':\s*\d+', text_original) or  # 端口号如 :27017
            re.search(r'[\w\.]+\.[\w\.]+', text_original) or  # 域名或包名
            re.search(r'\{.*\}', text_original) or  # JSON对象
            re.search(r'[\u4e00-\u9fa5]{5,}', text_original)  # 包含较长的中文段落（>=5个汉字）
        )
        
        # 如果包含章节编号或技术内容，不应被识别为水印
        if has_section_number or has_technical_content:
            return False
        
        # ⚠️ 策略1：优先使用坐标位置判断（最准确可靠）
        # 水印通常出现在页面中央区域或四个角落，且文本较短
        if coordinates and page_height > 0 and page_width > 0:
            y_pos = coordinates.get('y', 0)
            x_pos = coordinates.get('x', 0)
            element_height = coordinates.get('height', 0)
            element_width = coordinates.get('width', 0)
            element_center_y = y_pos + element_height / 2
            element_center_x = x_pos + element_width / 2
            
            # 水印位置特征：
            # 1. 页面中央区域（30%-70%的垂直位置，且水平位置也在30%-70%）
            is_in_center = (
                page_height * 0.30 < element_center_y < page_height * 0.70 and
                page_width * 0.30 < element_center_x < page_width * 0.70
            )
            
            # 2. 页面四个角落（顶部或底部20%，左侧或右侧20%）
            is_in_corner = (
                (y_pos < page_height * 0.20 or element_center_y > page_height * 0.80) and
                (x_pos < page_width * 0.20 or element_center_x > page_width * 0.80)
            )
            
            # 如果位置符合水印特征，且文本较短，进一步验证内容
            if (is_in_center or is_in_corner) and len(text_stripped) < 60:
                # 检查是否包含水印关键词
                watermark_keywords = [
                    '保密', 'CONFIDENTIAL', 'DRAFT', '草稿', '内部资料', 'INTERNAL',
                    '机密', 'SECRET', 'TOP SECRET', '绝密', 'RESTRICTED', '限制',
                    '禁止复制', 'DO NOT COPY', '样本', 'SAMPLE', '副本', 'COPY',
                ]
                for keyword in watermark_keywords:
                    if keyword.upper() in text_upper or keyword in text_original:
                        return True
                
                # 如果是很短文本（<20字符），位置又符合，很可能是水印
                if len(text_stripped) < 20:
                    return True
        
        # ⚠️ 策略2：如果没有坐标信息，使用内容特征判断（作为后备方案）
        # 常见水印关键词（中英文）
        watermark_keywords = [
            '保密', 'CONFIDENTIAL', 'DRAFT', '草稿', '内部资料', 'INTERNAL',
            '机密', 'SECRET', 'TOP SECRET', '绝密', 'RESTRICTED', '限制',
            '禁止复制', 'DO NOT COPY', '样本', 'SAMPLE', '副本', 'COPY',
            'NOT FOR DISTRIBUTION', '仅供内部使用'
        ]
        
        # 检查是否完全匹配水印关键词（只包含关键词本身，没有其他内容）
        if text_upper in [kw.upper() for kw in watermark_keywords]:
            return True
        
        # ⚠️ 优化：检查是否主要是水印关键词（文本内容主要就是水印关键词，而非包含在正常段落中）
        # 如果文本很短（<30字符）且主要是水印关键词，才认为是水印
        for keyword in watermark_keywords:
            keyword_upper = keyword.upper()
            if keyword_upper in text_upper or keyword in text_original:
                # 如果文本长度很短（<30字符），且水印关键词占比很高（>50%），才认为是水印
                if len(text_stripped) < 30:
                    # 计算关键词在文本中的占比
                    keyword_count = text_upper.count(keyword_upper) * len(keyword)
                    if keyword_count / len(text_stripped) > 0.5:
                        return True
                # 如果文本长度在30-50字符之间，要求关键词占比更高（>70%）且文本主要是水印短语
                elif len(text_stripped) < 50:
                    # 检查是否是完整的水印短语（如"内部资料,请勿外传!"）
                    watermark_phrases = [
                        r'内部资料[，,。.!！\s]*请勿外传',
                        r'CONFIDENTIAL',
                        r'DRAFT',
                        r'禁止复制',
                        r'DO NOT COPY',
                    ]
                    if any(re.search(phrase, text_original, re.IGNORECASE) for phrase in watermark_phrases):
                        return True
        
        # 检查重复的水印文本（如 "DRAFT DRAFT DRAFT"）
        words = text_upper.split()
        if len(words) >= 2:
            # 如果所有词都相同且是水印关键词
            if len(set(words)) == 1:
                word = words[0]
                # 检查这个词是否是水印关键词
                if any(word == kw.upper() or word in kw.upper() for kw in watermark_keywords):
                    if len(word) > 2:
                        return True
        
        return False
    
    def _is_cover_or_back_page(self, element_text: str, page_number: int, total_pages: int = 0, coordinates: Dict[str, Any] = None, page_height: float = 0, page_width: float = 0) -> bool:
        """
        判断元素是否属于封面或封底页
        
        封面/封底特征：
        1. 通常在文档的第一页或最后一页（⚠️ 优先使用页码判断）
        2. 包含标题、作者、出版社等元信息
        3. 格式通常特殊（居中、大字体等）
        4. 内容通常较短
        5. 位置可能在页面中央区域（封面）或底部区域（封底）
        
        判断策略（优先级）：
        1. 优先使用页码位置判断（第一页/最后一页）
        2. 结合坐标位置判断（页面中央或底部）
        3. 如果位置信息不可用，使用内容特征判断（关键词）
        """
        if not element_text:
            return False
        
        import re
        
        text_stripped = element_text.strip()
        text_lower = text_stripped.lower()
        
        # ⚠️ 策略1：优先使用页码位置判断（最准确）
        is_cover_page = page_number <= 2  # 封面通常在第一页或第二页
        is_back_page = False
        if total_pages > 0:
            is_back_page = page_number >= total_pages - 1  # 封底通常在最后一页或倒数第二页
        
        # ⚠️ 策略2：结合坐标位置判断（如果可用）
        # 封面：通常在页面中央区域（垂直30%-70%，水平30%-70%）
        # 封底：可能在页面底部区域
        is_in_center_area = False
        is_in_bottom_area = False
        
        if coordinates and page_height > 0 and page_width > 0:
            y_pos = coordinates.get('y', 0)
            x_pos = coordinates.get('x', 0)
            element_height = coordinates.get('height', 0)
            element_width = coordinates.get('width', 0)
            element_center_y = y_pos + element_height / 2
            element_center_x = x_pos + element_width / 2
            
            # 封面通常居中显示
            is_in_center_area = (
                page_height * 0.30 < element_center_y < page_height * 0.70 and
                page_width * 0.30 < element_center_x < page_width * 0.70
            )
            
            # 封底通常在底部
            is_in_bottom_area = element_center_y > page_height * 0.70
        
        # 封面关键词（通常在首页）
        cover_keywords = [
            r'封面', r'cover', r'书名', r'标题', r'title',
            r'作者', r'author', r'著', r'编', r'主编',
            r'出版社', r'publisher', r'press', r'出版日期',
            r'出版', r'published', r'isbn', r'issn'
        ]
        
        # 封底关键词（通常在末页）
        back_cover_keywords = [
            r'封底', r'back cover', r'封三', r'封四',
            r'定价', r'price', r'isbn', r'条码',
            r'责任编辑', r'责任校对', r'印刷'
        ]
        
        # 如果文本较短（封面封底通常内容简洁）
        is_short_text = len(text_stripped) < 300
        
        # 检查封面特征
        if is_cover_page:
            has_cover_keyword = any(re.search(keyword, text_lower, re.IGNORECASE) for keyword in cover_keywords)
            # 如果位置也符合（居中），更可能是封面
            if has_cover_keyword and is_short_text:
                if is_in_center_area or not coordinates:  # 居中或没有坐标信息
                    return True
            # 如果位置居中，即使没有关键词，也可能是封面标题
            elif is_in_center_area and is_short_text and len(text_stripped) < 100:
                return True
        
        # 检查封底特征
        if is_back_page:
            has_back_keyword = any(re.search(keyword, text_lower, re.IGNORECASE) for keyword in back_cover_keywords)
            # 如果位置也符合（底部），更可能是封底
            if has_back_keyword and is_short_text:
                return True
            # 如果位置在底部，即使没有关键词，也可能是封底信息
            elif is_in_bottom_area and is_short_text and len(text_stripped) < 100:
                return True
        else:
            # 如果没有总页数，仅通过内容判断
            has_back_keyword = any(re.search(keyword, text_lower, re.IGNORECASE) for keyword in back_cover_keywords)
            if has_back_keyword and is_short_text and len(text_stripped) < 200:
                return True
        
        return False
    
    def _is_footnote_or_margin_note(self, element_text: str, coordinates: Dict[str, Any], page_height: float = 0) -> bool:
        """
        判断元素是否是脚注或页边注释
        
        脚注/页边注释特征：
        1. 位置在页面底部或边缘
        2. 通常以数字、符号开头（如 [1]、①、*）
        3. 字体通常较小
        4. 内容通常较短
        5. 可能包含参考文献信息
        """
        if not element_text:
            return False
        
        text_stripped = element_text.strip()
        
        # 位置判断：如果在页面底部或边缘
        if coordinates and page_height > 0:
            y_pos = coordinates.get('y', 0)
            height = coordinates.get('height', 0)
            # 脚注通常在页面底部20%区域
            if y_pos + height > page_height * 0.8:
                # 进一步检查内容特征
                # 脚注通常以数字或符号开头
                if re.match(r'^[\[\(]*[0-9①②③④⑤⑥⑦⑧⑨⑩*†‡]+[\]\):：]*', text_stripped):
                    if len(text_stripped) < 200:  # 脚注通常较短
                        return True
        
        # 内容特征判断（即使没有坐标信息）
        # 1. 以脚注标记开头（如 [1], (1), * , ①等）
        footnote_patterns = [
            r'^[\[\(]*[0-9]+[\]\):：]',  # [1], (1), 1:
            r'^[①②③④⑤⑥⑦⑧⑨⑩]',  # 圆圈数字
            r'^[*†‡§]',  # 符号标记
            r'^\[注\d+\]',  # [注1]
            r'^注\s*\d+[:：]',  # 注1:
        ]
        
        if any(re.match(pattern, text_stripped) for pattern in footnote_patterns):
            # 如果是很短的文本（可能是页边注释）
            if len(text_stripped) < 100:
                return True
        
        # 2. 包含参考文献格式（如 "作者. 书名. 出版社, 年份"）
        reference_patterns = [
            r'.+\..+\..+\d{4}',  # 基本参考文献格式
            r'参见.*页',  # "参见第X页"
            r'见.*第.*页',  # "见第X页"
        ]
        
        # 如果匹配参考文献格式且文本较短
        if len(text_stripped) < 150:
            if any(re.search(pattern, text_stripped) for pattern in reference_patterns):
                return True
        
        return False
    
    def _detect_duplicate_content(self, current_text: str, previous_texts: List[str], similarity_threshold: float = 0.85) -> bool:
        """
        检测重复内容
        
        注意：标题或目录项在目录和正文中重复出现是正常的，不应被识别为重复内容
        
        参数:
            current_text: 当前文本
            previous_texts: 之前处理过的文本列表（用于对比）
            similarity_threshold: 相似度阈值（0-1）
        
        返回:
            True 如果检测到重复内容
        """
        if not current_text or not previous_texts:
            return False
        
        current_clean = _RE_WHITESPACE.sub(' ', current_text.strip())
        
        # 太短的文本不进行重复检测
        if len(current_clean) < MIN_TEXT_LENGTH_FOR_DUPLICATE:
            return False
        
        # ⚠️ 重要：检查是否是标题或目录项（包含章节编号）
        # 标题在目录和正文中重复出现是正常的，不应被识别为重复内容
        section_patterns = [
            r'\d+\.\d+(?:\.\d+)*',  # 1.1, 1.2.3, 1.2.3.4
            r'[一二三四五六七八九十]+[\.、]',  # 一、二、三、
            r'[IVX]+\.\d+',  # I.1, II.2.3
            r'第[一二三四五六七八九十\d]+[章节条]',  # 第一章、第二节
        ]
        # ✅ 修复作用域问题：在列表推导式外部导入 re 模块，或直接使用循环
        is_title_or_toc_item = False
        for pattern in section_patterns:
            if re.search(pattern, current_clean):
                is_title_or_toc_item = True
                break
        
        # 如果包含章节编号，即使完全重复也允许（标题可以重复出现）
        if is_title_or_toc_item:
            # 检查文本长度：如果是短标题（<50字符），允许重复
            # 如果是长段落重复，仍然认为是重复内容
            if len(current_clean) < 50:
                return False  # 短标题允许重复
        
        # 对于中文文本，使用字符级别比较；对于英文，使用单词级别
        # 检测是否包含中文字符
        has_chinese = bool(_RE_CHINESE.search(current_clean))
        
        for prev_text in previous_texts[-MAX_DUPLICATE_CHECK:]:  # 只检查最近N个文本，避免性能问题
            prev_clean = _RE_WHITESPACE.sub(' ', prev_text.strip())
            
            if len(prev_clean) < MIN_TEXT_LENGTH_FOR_DUPLICATE:
                continue
            
            # ⚠️ 修改：对于完全相同的短文本（可能是标题），如果文本较长（>50字符）才认为是重复
            # 如果是短文本且包含章节编号，允许重复（标题在目录和正文中都会出现）
            if current_clean.lower() == prev_clean.lower():
                # 如果是短文本（标题），允许重复
                if len(current_clean) < 50:
                    continue  # 跳过短文本的完全匹配检查，允许标题重复
                else:
                    # 长文本完全重复，认为是重复内容
                    return True
            
            # 计算文本相似度
            if has_chinese:
                # 中文：使用字符级别比较（更适合中文）
                current_chars = set(current_clean.lower())
                prev_chars = set(prev_clean.lower())
                
                # 移除空格和标点，只比较有意义字符
                current_chars = {c for c in current_chars if c.strip() and c not in '，。！？；：、'}
                prev_chars = {c for c in prev_chars if c.strip() and c not in '，。！？；：、'}
                
                if len(current_chars) < 5 or len(prev_chars) < 5:
                    continue
                
                intersection = len(current_chars & prev_chars)
                union = len(current_chars | prev_chars)
            else:
                # 英文：使用单词级别比较
                current_words = set(current_clean.lower().split())
                prev_words = set(prev_clean.lower().split())
                
                if len(current_words) < 3 or len(prev_words) < 3:
                    continue
                
                intersection = len(current_words & prev_words)
                union = len(current_words | prev_words)
            
            if union == 0:
                continue
            
            similarity = intersection / union
            
            # 如果相似度超过阈值，认为是重复内容
            if similarity >= similarity_threshold:
                # 进一步检查：如果文本长度相近且相似度很高
                length_ratio = min(len(current_clean), len(prev_clean)) / max(len(current_clean), len(prev_clean))
                if length_ratio > 0.85 and similarity >= 0.9:
                    return True
        
        return False
    
    def _cleanup_temp_files(self, temp_files: List[str], temp_dirs: List[str]) -> None:
        """
        清理临时文件和临时目录
        
        参数:
            temp_files: 需要清理的临时文件路径列表
            temp_dirs: 需要清理的临时目录路径列表
        """
        # 检查是否在调试模式下保留临时文件
        keep_temp = getattr(settings, 'DEBUG_KEEP_TEMP_FILES', False)
        if keep_temp:
            logger.debug(f"[临时文件清理] 调试模式：保留临时文件，文件={temp_files}, 目录={temp_dirs}")
            return
        
        # 清理临时文件
        for temp_file in temp_files:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.debug(f"[临时文件清理] 已删除临时文件: {temp_file}")
                except Exception as e:
                    logger.warning(f"[临时文件清理] 删除临时文件失败: {temp_file}, 错误: {e}")
        
        # 清理临时目录（注意：目录必须在文件之后清理，且目录为空才能删除）
        for temp_dir in temp_dirs:
            if temp_dir and os.path.isdir(temp_dir):
                try:
                    # 先尝试删除目录内的所有文件
                    try:
                        for item in os.listdir(temp_dir):
                            item_path = os.path.join(temp_dir, item)
                            if os.path.isfile(item_path):
                                os.remove(item_path)
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                    except Exception as e:
                        logger.debug(f"[临时文件清理] 清理临时目录内容时出错: {e}")
                    
                    # 删除空目录
                    try:
                        os.rmdir(temp_dir)
                        logger.debug(f"[临时文件清理] 已删除临时目录: {temp_dir}")
                    except OSError:
                        # 如果目录不为空或删除失败，尝试使用shutil强制删除
                        try:
                            shutil.rmtree(temp_dir)
                            logger.debug(f"[临时文件清理] 已强制删除临时目录: {temp_dir}")
                        except Exception as e:
                            logger.warning(f"[临时文件清理] 删除临时目录失败: {temp_dir}, 错误: {e}")
                except Exception as e:
                    logger.warning(f"[临时文件清理] 处理临时目录失败: {temp_dir}, 错误: {e}")
    
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
    
    def _process_parsed_elements(self, elements: List, file_path: str, file_size: int, is_pdf: Optional[bool] = None) -> Dict[str, Any]:
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
            file_type = os.path.splitext(file_path)[1].lower()
            
            # 如果未明确指定is_pdf，则根据文件扩展名判断
            # 但如果明确指定了（如Word转PDF的情况），使用指定的值
            if is_pdf is None:
                is_pdf = file_type == '.pdf'
            
            metadata = {
                'file_size': file_size,
                'file_type': file_type,
                'element_count': len(elements),
                'parsing_timestamp': datetime.utcnow().isoformat() + "Z",
                'is_pdf': is_pdf  # 标记是否为PDF文件（包括转换后的PDF）
            }
            
            # PDF文件的特殊处理提示
            if is_pdf:
                if file_type == '.pdf':
                    logger.debug("检测到PDF文件，将应用增强的OCR噪声过滤策略")
                else:
                    logger.debug(f"检测到转换后的PDF（原文件: {file_type}），将应用增强的OCR噪声过滤策略")
            
            # 边界情况处理：如果elements为空，直接返回
            if not elements or len(elements) == 0:
                logger.warning(f"解析结果为空，elements列表为空")
                return {
                    "text_content": "",
                    "images": [],
                    "tables": [],
                    "metadata": metadata,
                    "char_count": 0,
                    "word_count": 0,
                    "element_count": 0,
                    "text_element_index_map": []
                }
            
            # 获取页面高度和宽度信息（用于位置判断）和总页数信息（用于封面/封底判断）
            # 优化：在第一个循环中同时计算，避免重复遍历
            page_height = 0
            page_width = 0
            max_page_number = 1
            
            # 遍历所有元素以获取准确的页面尺寸和最大页码
            # 注意：这里只遍历一次，后续处理循环会再次遍历，但这次遍历是必需的
            for elem in elements:
                # 获取页码信息
                elem_meta = getattr(elem, 'metadata', None)
                page_num = _meta_get(elem_meta, 'page_number', 1)
                if page_num > max_page_number:
                    max_page_number = page_num
                
                # 获取坐标信息以估算页面尺寸
                coords = self._extract_coordinates(elem)
                if coords and coords.get('height', 0) > 0:
                    # 根据坐标估算页面高度（y坐标 + 元素高度）
                    element_bottom = coords.get('y', 0) + coords.get('height', 0)
                    if element_bottom > page_height:
                        page_height = element_bottom
                    
                    # 根据坐标估算页面宽度（x坐标 + 元素宽度）
                    element_right = coords.get('x', 0) + coords.get('width', 0)
                    if element_right > page_width:
                        page_width = element_right
            
            # 如果没有获取到，使用标准A4尺寸作为默认值
            if page_height == 0:
                page_height = DEFAULT_PAGE_HEIGHT
                logger.warning(f"[PDF诊断] 无法从元素坐标计算页面高度，使用默认值: {page_height}")
            else:
                logger.debug(f"[PDF诊断] 计算得到的页面高度: {page_height}")
            if page_width == 0:
                page_width = 595  # A4宽度（点），标准A4纸张尺寸：595×842点
                logger.warning(f"[PDF诊断] 无法从元素坐标计算页面宽度，使用默认值: {page_width}")
            else:
                logger.debug(f"[PDF诊断] 计算得到的页面宽度: {page_width}")
            
            # ✅ PDF诊断：记录坐标信息统计
            if is_pdf:
                coordinates_count = 0
                coordinates_with_valid_y = 0
                coordinates_with_valid_x = 0
                y_positions = []
                for elem in elements[:50]:  # 只检查前50个元素（避免太多日志）
                    coords = self._extract_coordinates(elem)
                    if coords and (coords.get('x', 0) > 0 or coords.get('y', 0) > 0):
                        coordinates_count += 1
                        y_pos = coords.get('y', 0)
                        x_pos = coords.get('x', 0)
                        if y_pos > 0:
                            coordinates_with_valid_y += 1
                            y_positions.append(y_pos)
                        if x_pos > 0:
                            coordinates_with_valid_x += 1
                
                logger.info(f"[PDF诊断] 坐标信息统计: 前50个元素中, 有坐标={coordinates_count}, "
                           f"有效Y坐标={coordinates_with_valid_y}, 有效X坐标={coordinates_with_valid_x}")
                if y_positions:
                    logger.info(f"[PDF诊断] Y坐标范围: min={min(y_positions):.1f}, max={max(y_positions):.1f}, "
                               f"平均={sum(y_positions)/len(y_positions):.1f}")
                    # 如果Y坐标的最大值小于页面高度的80%，可能坐标系统有问题
                    if max(y_positions) < page_height * 0.8:
                        logger.warning(f"[PDF诊断] ⚠️ 警告: Y坐标最大值({max(y_positions):.1f})明显小于页面高度({page_height}), "
                                      f"可能是坐标系统不准确，页眉页脚检测可能失效")
            
            # 用于统计过滤信息的计数器
            filter_stats = {
                'blank_content': 0,
                'header_footer': 0,
                'noise_text': 0,
                'copyright': 0,
                'watermark': 0,
                'cover_page': 0,
                'footnote': 0,
                'duplicate': 0,
                'toc_converted': 0
            }
            
            # 用于重复内容检测的文本历史记录
            previous_texts = []  # 存储已处理的有效文本（用于重复检测）
            
            for element_index, element in enumerate(elements):
                element_text = getattr(element, 'text', '')
                element_category = getattr(element, 'category', 'Unknown')
                
                # 基础清洗：去除回车、合并多空格、修复被换行打断的行
                if element_text:
                    element_text = element_text.replace('\r', '')
                    # 连续空格/制表符归一（使用预编译的正则表达式）
                    element_text = _RE_TABS.sub(" ", element_text)
                    element_text = _RE_MULTI_SPACES.sub(" ", element_text)
                
                # 获取坐标和页码信息
                coordinates = self._extract_coordinates(element)
                page_number = _meta_get(getattr(element, 'metadata', None), 'page_number', 1)
                
                # ========== 文档降噪处理 ==========
                # 使用try-except确保单个过滤器失败不影响整体处理
                
                # 1. 空白内容过滤（优先处理）
                if settings.ENABLE_BLANK_CONTENT_FILTER:
                    try:
                        if self._is_blank_content(element_text):
                            filter_stats['blank_content'] += 1
                            logger.debug(f"检测到空白内容，跳过元素 {element_index}")
                            continue
                    except Exception as e:
                        logger.warning(f"空白内容过滤出错: {e}，继续处理元素 {element_index}")
                
                # ⚠️ 重要：通用内容保护机制
                # 在所有降噪过滤器之前，先检查是否是有效的文档内容
                # 如果是有效内容（如章节标题、技术内容、有意义段落等），跳过所有降噪过滤
                is_valid_content = False
                if element_text:
                    try:
                        is_valid_content = self._is_valid_content(element_text)
                        if is_valid_content:
                            logger.debug(f"检测到有效内容，跳过所有降噪过滤: 元素 {element_index}: {element_text[:50]}...")
                    except Exception as e:
                        logger.warning(f"内容保护检查出错: {e}，继续处理元素 {element_index}")
                
                # 2. 页眉页脚过滤
                # ⚠️ 注意：如果是有效内容，跳过此过滤器
                if not is_valid_content and settings.ENABLE_HEADER_FOOTER_FILTER:
                    try:
                        if element_text:
                            is_header_footer = self._is_header_or_footer(element_text, element_category, coordinates, page_number, page_height)
                            if is_header_footer:
                                filter_stats['header_footer'] += 1
                                # ✅ PDF诊断：记录页眉页脚检测详情
                                if is_pdf:
                                    y_pos = coordinates.get('y', 0) if coordinates else 0
                                    element_height = coordinates.get('height', 0) if coordinates else 0
                                    element_bottom = y_pos + element_height
                                    header_ratio = (y_pos / page_height) if page_height > 0 else 0
                                    footer_ratio = (element_bottom / page_height) if page_height > 0 else 0
                                    logger.info(f"[PDF诊断] 检测到页眉页脚: 元素 {element_index}, "
                                               f"文本='{element_text[:30]}...', "
                                               f"页码={page_number}, "
                                               f"Y位置={y_pos:.1f} (占页面{header_ratio:.1%}), "
                                               f"底部={element_bottom:.1f} (占页面{footer_ratio:.1%}), "
                                               f"页面高度={page_height:.1f}")
                                else:
                                    logger.debug(f"检测到页眉页脚，跳过元素 {element_index}: {element_text[:50]}...")
                                continue
                    except Exception as e:
                        logger.warning(f"页眉页脚过滤出错: {e}，继续处理元素 {element_index}")
                
                # 3. 噪声文本过滤（OCR错误、碎片文本等）
                # PDF文件使用更严格的OCR噪声过滤
                # ⚠️ 注意：如果是有效内容，跳过此过滤器
                if not is_valid_content and settings.ENABLE_NOISE_TEXT_FILTER:
                    try:
                        if self._is_noise_text(element_text, is_pdf=is_pdf):
                            filter_stats['noise_text'] += 1
                            logger.debug(f"检测到噪声文本{'（PDF OCR错误）' if is_pdf else ''}，跳过元素 {element_index}: {element_text[:50]}...")
                            continue
                    except Exception as e:
                        logger.warning(f"噪声文本过滤出错: {e}，继续处理元素 {element_index}")
                
                # 4. 版权声明页过滤
                # ⚠️ 注意：如果是有效内容，跳过此过滤器
                if not is_valid_content and settings.ENABLE_COPYRIGHT_FILTER:
                    try:
                        if self._is_copyright_page(element_text, page_number, max_page_number, coordinates):
                            filter_stats['copyright'] += 1
                            logger.debug(f"检测到版权声明，跳过元素 {element_index}: {element_text[:50]}...")
                            continue
                    except Exception as e:
                        logger.warning(f"版权声明过滤出错: {e}，继续处理元素 {element_index}")
                
                # 5. 水印过滤
                # ⚠️ 注意：如果是有效内容，跳过此过滤器
                if not is_valid_content and settings.ENABLE_WATERMARK_FILTER:
                    try:
                        if self._is_watermark(element_text, coordinates, page_number, page_height, page_width):
                            filter_stats['watermark'] += 1
                            logger.debug(f"检测到水印，跳过元素 {element_index}: {element_text[:50]}...")
                            continue
                    except Exception as e:
                        logger.warning(f"水印过滤出错: {e}，继续处理元素 {element_index}")
                
                # 6. 封面/封底页过滤
                # ⚠️ 注意：如果是有效内容，跳过此过滤器
                if not is_valid_content and settings.ENABLE_COVER_PAGE_FILTER:
                    try:
                        if self._is_cover_or_back_page(element_text, page_number, max_page_number, coordinates, page_height, page_width):
                            filter_stats['cover_page'] += 1
                            logger.debug(f"检测到封面/封底页，跳过元素 {element_index}: {element_text[:50]}...")
                            continue
                    except Exception as e:
                        logger.warning(f"封面/封底页过滤出错: {e}，继续处理元素 {element_index}")
                
                # 7. 脚注/页边注释过滤（可选，某些脚注可能是有用的）
                # ⚠️ 注意：如果是有效内容，跳过此过滤器
                if not is_valid_content and settings.ENABLE_FOOTNOTE_FILTER:
                    try:
                        if self._is_footnote_or_margin_note(element_text, coordinates, page_height):
                            filter_stats['footnote'] += 1
                            logger.debug(f"检测到脚注/页边注释，跳过元素 {element_index}: {element_text[:50]}...")
                            continue
                    except Exception as e:
                        logger.warning(f"脚注过滤出错: {e}，继续处理元素 {element_index}")
                
                # 8. 重复内容检测（在处理文本元素时检测）
                # 注意：重复检测需要在文本提取之前进行，但只对文本元素生效
                
                # 检查表格是否是目录（目录应该作为文本处理，而不是表格）
                is_toc = False
                if settings.ENABLE_TOC_DETECTION:
                    try:
                        if element_category == 'Table' and element_text:
                            if self._is_table_of_contents(element_text, element_category, coordinates, page_number):
                                filter_stats['toc_converted'] += 1
                                logger.info(f"检测到目录（被误识别为表格），转换为文本处理: 元素 {element_index}")
                                # 将目录作为文本处理，而不是表格
                                element_category = 'NarrativeText'  # 临时修改类别，使其进入文本处理分支
                                is_toc = True  # 标记为目录，避免进入表格处理分支
                    except Exception as e:
                        logger.warning(f"目录识别出错: {e}，继续处理元素 {element_index}")
                
                # 处理文本元素（包括 Title, NarrativeText, ListItem 等，以及被识别为目录的表格）
                if element_text and element_category not in ['Image', 'Table']:
                    # 8. 重复内容检测（仅对文本元素进行）
                    # ⚠️ 注意：标题和目录项在目录和正文中重复出现是正常的，不应被过滤
                    if settings.ENABLE_DUPLICATE_DETECTION:
                        try:
                            # 检查是否是标题或目录项（包含章节编号的短文本）
                            section_patterns = [
                                r'^\d+\.',  # 单数字加点开头，如 1.、4. 等
                                r'\d+\.\d+(?:\.\d+)*',  # 1.1, 1.2.3, 1.2.3.3.1
                                r'[一二三四五六七八九十]+[\.、]',  # 一、二、三、
                                r'[IVX]+\.\d+',  # I.1, II.2
                                r'第[一二三四五六七八九十\d]+[章节条]',  # 第一章、第二节
                            ]
                            text_clean = element_text.strip()
                            
                            # ⚠️ 优化：放宽标题检测条件，即使文本较长（<150字符）也允许
                            # 因为标题可能包含一些描述性文字，如"1.2.3.3.1.停主节点 mongo-0 是否切换..."
                            # ✅ 修复作用域问题：使用循环代替生成器表达式
                            is_title_or_toc = False
                            for pattern in section_patterns:
                                if re.search(pattern, text_clean):
                                    is_title_or_toc = True
                                    break
                            
                            # 如果包含章节编号，无论是短文本还是稍长的文本（<150字符），都允许重复
                            if is_title_or_toc and len(text_clean) < 150:
                                logger.debug(f"检测到标题/目录项（包含章节编号），允许重复出现: 元素 {element_index}: {element_text[:50]}...")
                            else:
                                # 非标题内容才进行重复检测
                                if self._detect_duplicate_content(element_text, previous_texts):
                                    filter_stats['duplicate'] += 1
                                    logger.debug(f"检测到重复内容，跳过元素 {element_index}: {element_text[:50]}...")
                                    continue  # 跳过重复内容
                        except Exception as e:
                            logger.warning(f"重复内容检测出错: {e}，继续处理元素 {element_index}")
                    
                    # 添加到文本内容
                    text_start_pos = current_text_pos
                    text_end_pos = current_text_pos + len(element_text)
                    text_content += element_text + "\n"
                    # 记录文本段落的 element_index 映射
                    text_element_index_map.append({
                        'start_pos': text_start_pos,
                        'end_pos': text_end_pos - 1,  # 减去换行符
                        'element_index': element_index,
                        'element_type': element.category,  # 使用原始类别
                        'page_number': page_number,
                        'coordinates': coordinates
                    })
                    current_text_pos = text_end_pos + 1  # +1 for \n
                    
                    # 将处理后的文本添加到历史记录（用于重复检测）
                    if settings.ENABLE_DUPLICATE_DETECTION:
                        previous_texts.append(element_text)
                        # 限制历史记录大小，避免内存占用过大
                        if len(previous_texts) > MAX_PREVIOUS_TEXTS:
                            previous_texts.pop(0)  # 移除最旧的记录
                
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
                # ✅ 修复：表格应该独立成块，不参与文本分块，避免表格结构被破坏
                # 表格通过 element_index 在后续合并时插入到正确位置，保持原文档顺序
                elif element.category == 'Table' and not is_toc:
                    elem_id = getattr(element, 'element_id', getattr(element, 'id', None))
                    
                    # ✅ 优化：从 table_data 中提取更完整的表格文本表示
                    table_data_result = self._extract_table_data(element)
                    
                    # ✅ 优化：优先使用结构化数据生成表格文本，避免OCR错误
                    # 策略优先级：cells > html提取 > element_text（OCR文本，可能有错误）
                    table_text_optimized = None
                    
                    # 1. 优先使用结构化的 cells 数据生成文本（最准确）
                    if table_data_result.get('cells'):
                        try:
                            cells = table_data_result['cells']
                            text_lines = []
                            for row in cells:
                                if isinstance(row, (list, tuple)):
                                    # 使用制表符分隔，保持列对齐
                                    text_lines.append('\t'.join(str(cell) if cell is not None else '' for cell in row))
                                else:
                                    text_lines.append(str(row))
                            if text_lines:
                                table_text_optimized = '\n'.join(text_lines)
                                logger.debug(f"从结构化 cells 数据生成表格文本: {len(text_lines)} 行")
                        except Exception as e:
                            logger.debug(f"从结构化 cells 数据生成表格文本失败: {e}")
                    
                    # 2. 如果没有 cells，尝试从 HTML 中正确提取表格结构文本（比OCR文本更准确）
                    if not table_text_optimized and table_data_result.get('html'):
                        try:
                            import re
                            html_text = table_data_result['html']
                            
                            # ✅ 修复：正确解析 HTML 表格结构，保持行列关系
                            # 方法1：使用 BeautifulSoup（如果可用）
                            try:
                                from bs4 import BeautifulSoup
                                soup = BeautifulSoup(html_text, 'html.parser')
                                table = soup.find('table')
                                if table:
                                    text_lines = []
                                    for tr in table.find_all('tr'):
                                        row_cells = []
                                        for td in tr.find_all(['td', 'th']):
                                            cell_text = td.get_text(strip=True)
                                            row_cells.append(cell_text)
                                        if row_cells:
                                            # 使用制表符分隔同一行的单元格
                                            text_lines.append('\t'.join(row_cells))
                                    
                                    if text_lines:
                                        # 使用换行符分隔不同行
                                        table_text_optimized = '\n'.join(text_lines)
                                        logger.debug(f"从 HTML (BeautifulSoup) 提取表格文本: {len(text_lines)} 行")
                            except ImportError:
                                # 方法2：使用正则表达式解析（兜底方案）
                                tr_pattern = r'<tr[^>]*>(.*?)</tr>'
                                td_pattern = r'<t[dh][^>]*>(.*?)</t[dh]>'
                                
                                trs = re.findall(tr_pattern, html_text, re.DOTALL | re.IGNORECASE)
                                if trs:
                                    text_lines = []
                                    for tr_content in trs:
                                        tds = re.findall(td_pattern, tr_content, re.DOTALL | re.IGNORECASE)
                                        if tds:
                                            # 清理每个单元格内容
                                            row_cells = []
                                            for td in tds:
                                                # 移除内嵌的 HTML 标签
                                                cell_text = re.sub(r'<[^>]+>', '', td)
                                                # 处理 HTML 实体
                                                cell_text = cell_text.replace('&nbsp;', ' ').replace('&amp;', '&')
                                                cell_text = cell_text.replace('&lt;', '<').replace('&gt;', '>')
                                                # 规范化空白字符
                                                cell_text = ' '.join(cell_text.split())
                                                row_cells.append(cell_text.strip())
                                            
                                            if row_cells:
                                                # 使用制表符分隔同一行的单元格
                                                text_lines.append('\t'.join(row_cells))
                                    
                                    if text_lines:
                                        # 使用换行符分隔不同行
                                        table_text_optimized = '\n'.join(text_lines)
                                        logger.debug(f"从 HTML (正则) 提取表格文本: {len(text_lines)} 行")
                        except Exception as e:
                            logger.warning(f"从 HTML 提取表格文本失败: {e}")
                    
                    # 3. 最后才使用 element_text（可能包含OCR错误）
                    if not table_text_optimized:
                        table_text_optimized = element_text
                        if is_pdf:
                            logger.warning(f"表格文本只能从OCR文本生成，可能包含OCR错误: {element_text[:50]}...")
                        else:
                            logger.debug(f"使用原始 element_text 作为表格文本")
                    
                    table_info = {
                        'element_id': elem_id,
                        'element_index': element_index,  # 关键：记录元素在原始elements中的索引
                        'page_number': page_number,
                        'coordinates': coordinates,
                        'table_data': table_data_result,
                        'table_text': table_text_optimized  # ✅ 使用优化后的表格文本
                    }
                    tables.append(table_info)
                    # ✅ 重要：表格不添加到 text_content，避免被分块算法分割
                    # 表格会作为独立块，通过 element_index 在后续按顺序插入
                    logger.info(f"✅ 提取表格（element_index={element_index}）: {table_data_result.get('rows', 0)} 行 x {table_data_result.get('columns', 0)} 列, 文本长度={len(table_text_optimized)}")
            
            # 提取文档属性
            doc_metadata = self._extract_document_metadata(elements)
            metadata.update(doc_metadata)
            
            # 添加过滤统计信息
            total_filtered = sum(filter_stats.values())
            metadata['filter_stats'] = {
                **filter_stats,
                'total_filtered': total_filtered,
                'filter_rate': total_filtered / len(elements) if len(elements) > 0 else 0.0
            }
            
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
            
            # 记录过滤统计信息到日志
            if total_filtered > 0:
                pdf_note = "（PDF文件，已应用增强OCR噪声过滤）" if is_pdf else ""
                logger.info(f"文档降噪统计{pdf_note}: 总元素={len(elements)}, 过滤={total_filtered}, "
                           f"过滤率={metadata['filter_stats']['filter_rate']:.2%}, "
                           f"详情={filter_stats}")
            
            # ✅ PDF诊断：检查降噪准确性
            if is_pdf:
                # 计算页眉页脚过滤率
                header_footer_rate = filter_stats.get('header_footer', 0) / len(elements) if len(elements) > 0 else 0
                noise_rate = filter_stats.get('noise_text', 0) / len(elements) if len(elements) > 0 else 0
                
                logger.info(f"[PDF诊断] 降噪准确性分析:")
                logger.info(f"[PDF诊断]   页眉页脚过滤: {filter_stats.get('header_footer', 0)} 个元素 ({header_footer_rate:.1%})")
                logger.info(f"[PDF诊断]   噪声文本过滤: {filter_stats.get('noise_text', 0)} 个元素 ({noise_rate:.1%})")
                logger.info(f"[PDF诊断]   总过滤率: {metadata['filter_stats']['filter_rate']:.1%}")
                
                # 警告：如果页眉页脚过滤率过低（<2%），可能存在问题
                if header_footer_rate < 0.02 and len(elements) > 50:
                    logger.warning(f"[PDF诊断] ⚠️ 警告: 页眉页脚过滤率过低 ({header_footer_rate:.1%})，"
                                 f"可能页眉页脚未被正确识别。请检查坐标信息是否准确。")
                
                # 警告：如果总过滤率过高（>50%），可能过度过滤
                if metadata['filter_stats']['filter_rate'] > 0.50:
                    logger.warning(f"[PDF诊断] ⚠️ 警告: 总过滤率过高 ({metadata['filter_stats']['filter_rate']:.1%})，"
                                 f"可能误过滤了正常内容。请检查降噪逻辑。")
            
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
        """提取表格数据 - 优化版，支持更完整的表格结构提取"""
        try:
            table_data: Dict[str, Any] = {
                'rows': 0,
                'columns': 0,
                'cells': [],
                'structure': 'unknown'
            }

            # ✅ 优化：使用 unstructured.staging.base 的表格转换功能
            # 这样可以获取更完整的表格结构数据
            try:
                from unstructured.staging.base import elements_to_json
                # 将单个表格元素转换为 JSON，获取完整结构
                element_json = elements_to_json([element])
                if element_json and len(element_json) > 0:
                    elem_data = element_json[0]
                    # 检查是否有结构化的表格数据
                    if isinstance(elem_data, dict):
                        # 优先使用 text_as_html（最完整的结构）
                        html = elem_data.get('metadata', {}).get('text_as_html') or \
                               elem_data.get('metadata', {}).get('table_html') or \
                               elem_data.get('text_as_html')
                        if html:
                            table_data['html'] = html
                            logger.debug(f"从 element_json 提取到 HTML 表格数据，长度: {len(html)}")
            except Exception as e:
                logger.debug(f"尝试从 elements_to_json 提取表格数据失败: {e}")

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
                        # ✅ 新增：尝试调用 to_dict() 方法获取元数据
                        try:
                            if hasattr(meta, 'to_dict'):
                                meta_dict = meta.to_dict()
                                val = meta_dict.get(k)
                                if val:
                                    html = val
                                    break
                        except Exception:
                            pass
            if html and 'html' not in table_data:
                table_data['html'] = html
                logger.debug(f"提取到 HTML 表格数据，长度: {len(html)}")

            # 2) ✅ 优化：提取结构化表格数据（如果启用了 infer_table_structure）
            # unstructured 库在启用表格结构识别时，会在 metadata 中存储更完整的表格数据
            meta = getattr(element, 'metadata', None)
            cells_from_meta = None
            
            if meta:
                # 尝试从 metadata 中获取结构化单元格数据
                meta_dict = None
                if isinstance(meta, dict):
                    meta_dict = meta
                elif hasattr(meta, 'to_dict'):
                    try:
                        meta_dict = meta.to_dict()
                    except Exception:
                        pass
                
                if meta_dict:
                    # 检查是否有 cells 或 table_structure 数据
                    cells_from_meta = meta_dict.get('cells') or \
                                     meta_dict.get('table_cells') or \
                                     meta_dict.get('structure', {}).get('cells')
                    
                    if cells_from_meta:
                        logger.debug(f"从 metadata 提取到结构化单元格数据: {len(cells_from_meta)} 行")
                        table_data['cells'] = cells_from_meta
                        table_data['rows'] = len(cells_from_meta)
                        table_data['columns'] = max((len(r) if isinstance(r, (list, tuple)) else 1 for r in cells_from_meta), default=0)
                        table_data['structure'] = 'structured'

            # 3) ✅ 如果 HTML 存在但 cells 不存在，从 HTML 中解析 cells（最准确）
            if not cells_from_meta and table_data.get('html'):
                try:
                    import html.parser
                    from html.parser import HTMLParser
                    from io import StringIO
                    
                    html_content = table_data['html']
                    # 使用 BeautifulSoup 或正则表达式解析 HTML 表格
                    # 如果没有 BeautifulSoup，使用简单的正则表达式解析
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html_content, 'html.parser')
                        table = soup.find('table')
                        if table:
                            cells_from_html = []
                            for tr in table.find_all('tr'):
                                row = []
                                for td in tr.find_all(['td', 'th']):
                                    cell_text = td.get_text(strip=True)
                                    row.append(cell_text)
                                if row:  # 只添加非空行
                                    cells_from_html.append(row)
                            
                            if cells_from_html and len(cells_from_html) > 0:
                                # 验证解析结果：至少要有2列或2行，或者HTML确实包含表格结构
                                first_row_cols = len(cells_from_html[0]) if cells_from_html else 0
                                if first_row_cols >= 2 or len(cells_from_html) >= 2:
                                    table_data['cells'] = cells_from_html
                                    table_data['rows'] = len(cells_from_html)
                                    table_data['columns'] = max((len(r) for r in cells_from_html), default=0)
                                    table_data['structure'] = 'html_parsed'
                                    cells_from_meta = cells_from_html  # 标记已找到，避免继续执行文本解析
                                    logger.info(f"✅ 从 HTML 解析出表格 cells: {table_data['rows']} 行 x {table_data['columns']} 列")
                    except ImportError:
                        # 如果没有 BeautifulSoup，使用正则表达式简单解析
                        import re
                        # 提取所有 tr 标签中的内容
                        tr_pattern = r'<tr[^>]*>(.*?)</tr>'
                        td_pattern = r'<t[dh][^>]*>(.*?)</t[dh]>'
                        
                        trs = re.findall(tr_pattern, html_content, re.DOTALL | re.IGNORECASE)
                        if trs:
                            cells_from_html = []
                            for tr_content in trs:
                                tds = re.findall(td_pattern, tr_content, re.DOTALL | re.IGNORECASE)
                                if tds:
                                    # 清理 HTML 标签和实体
                                    row = []
                                    for td in tds:
                                        # 移除内嵌的 HTML 标签和实体
                                        cell_text = re.sub(r'<[^>]+>', '', td)
                                        cell_text = cell_text.replace('&nbsp;', ' ').replace('&amp;', '&')
                                        cell_text = cell_text.replace('&lt;', '<').replace('&gt;', '>')
                                        cell_text = ' '.join(cell_text.split())  # 规范化空白字符
                                        row.append(cell_text)
                                    if row:
                                        cells_from_html.append(row)
                            
                            if cells_from_html and len(cells_from_html) > 0:
                                first_row_cols = len(cells_from_html[0]) if cells_from_html else 0
                                if first_row_cols >= 2 or len(cells_from_html) >= 2:
                                    table_data['cells'] = cells_from_html
                                    table_data['rows'] = len(cells_from_html)
                                    table_data['columns'] = max((len(r) for r in cells_from_html), default=0)
                                    table_data['structure'] = 'html_parsed_regex'
                                    cells_from_meta = cells_from_html
                                    logger.info(f"✅ 从 HTML (正则) 解析出表格 cells: {table_data['rows']} 行 x {table_data['columns']} 列")
                except Exception as e:
                    logger.warning(f"从 HTML 解析 cells 失败: {e}")
            
            # 4) 兜底：将表格文本按 \n / \t 拆分成二维数组
            # ⚠️ 只在没有从 metadata 和 HTML 获取到结构化数据时才使用此方法
            if not cells_from_meta:
                text = getattr(element, 'text', '') or ''
                if text:
                    # ✅ 优化：尝试多种分隔符，提高解析准确性
                    # 表格文本可能使用制表符、多个空格、或管道符分隔
                    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
                    cells: List[List[str]] = []
                    
                    for ln in lines:
                        # 尝试制表符分隔
                        if '\t' in ln:
                            cols = [c.strip() for c in ln.split('\t') if c.strip()]
                        # 尝试管道符分隔（Markdown 表格格式）
                        elif '|' in ln:
                            cols = [c.strip() for c in ln.split('|') if c.strip()]
                            # 移除可能的表头/表尾分隔符（如 |---|---|）
                            cols = [c for c in cols if not all(char in ['-', ':', ' '] for char in c)]
                        # 尝试多个空格分隔
                        else:
                            # 使用正则表达式分割多个连续空格
                            cols = _RE_MULTI_SPACES.split(ln)
                            cols = [c.strip() for c in cols if c.strip()]
                        
                        if cols:
                            cells.append(cols)
                    
                    # ⚠️ 重要：验证解析结果，避免单个长字符串被当作有效单元格
                    if cells:
                        # 检查是否为有效的表格结构（至少2列或2行）
                        first_row_cols = len(cells[0]) if cells else 0
                        if first_row_cols >= 2 or len(cells) >= 2:
                            table_data['cells'] = cells
                            table_data['rows'] = len(cells)
                            table_data['columns'] = max((len(r) for r in cells), default=0)
                            table_data['structure'] = 'tsv'
                            logger.debug(f"从文本提取到表格数据: {table_data['rows']} 行 x {table_data['columns']} 列")
                        else:
                            # 如果解析出来的结构无效（只有1行1列），且 HTML 存在，不要覆盖
                            if not table_data.get('html'):
                                logger.warning(f"⚠️ 从文本解析出的表格结构无效（{len(cells)} 行 x {first_row_cols} 列），且没有 HTML，保留解析结果")
                                table_data['cells'] = cells
                                table_data['rows'] = len(cells)
                                table_data['columns'] = first_row_cols
                                table_data['structure'] = 'tsv_invalid'
                            else:
                                logger.warning(f"⚠️ 从文本解析出的表格结构无效（{len(cells)} 行 x {first_row_cols} 列），但 HTML 存在，跳过文本解析结果")

            # ✅ 记录表格数据的完整性
            if table_data['cells']:
                total_cells = sum(len(row) for row in table_data['cells'])
                logger.info(f"✅ 表格数据提取完成: {table_data['rows']} 行 x {table_data['columns']} 列, 共 {total_cells} 个单元格")
            elif table_data.get('html'):
                logger.info(f"✅ 表格 HTML 提取完成: {len(table_data['html'])} 字符")
            else:
                logger.warning(f"⚠️ 表格数据提取不完整: 仅获取到文本，可能丢失结构信息")

            return table_data
            
        except Exception as e:
            logger.error(f"提取表格数据错误: {e}", exc_info=True)
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