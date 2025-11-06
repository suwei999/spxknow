import os
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.logging import logger


class DocxService:
    """
    DOCX 文档解析服务（完全本地，基于 python-docx），不依赖 Unstructured。
    输出结构与现有任务流兼容：
      - text_content: str
      - tables: [{element_index, table_data{cells/html/rows/columns}, table_text, page_number=None}]
      - images: [{data/bytes, element_index(None), page_number=None}]
      - text_element_index_map: [{element_index, element_type}]
      - filtered_elements_light: [{category, text, element_index}]
    """

    def __init__(self, db: Session):
        self.db = db

    def parse_document(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        try:
            from docx import Document  # type: ignore
        except Exception as e:
            raise RuntimeError("缺少依赖 python-docx，请先安装: pip install python-docx") from e

        logger.info(f"[DOCX] 开始本地解析: {file_path}")
        doc = Document(file_path)

        text_content_parts: List[str] = []
        tables: List[Dict[str, Any]] = []
        images: List[Dict[str, Any]] = []
        text_element_index_map: List[Dict[str, Any]] = []
        filtered_elements_light: List[Dict[str, Any]] = []

        element_index = 0
        # 用于记录图片的 element_index（key: 图片的 rId，value: element_index）
        image_element_index_map: Dict[str, int] = {}

        # 按照文档实际顺序遍历段落与表格
        try:
            from docx.oxml.ns import qn  # type: ignore
            from docx.text.paragraph import Paragraph  # type: ignore
            from docx.table import Table as DxTable  # type: ignore

            def iter_block_items(d):
                body = d.element.body
                for child in body.iterchildren():
                    tag = child.tag
                    if tag == qn('w:p'):
                        yield 'paragraph', Paragraph(child, d)
                    elif tag == qn('w:tbl'):
                        yield 'table', DxTable(child, d)

            for kind, item in iter_block_items(doc):
                if kind == 'paragraph':
                    p = item
                    
                    # ✅ 检查段落中是否包含图片（内联图片）
                    try:
                        if hasattr(p, 'runs'):
                            for run in p.runs:
                                if hasattr(run, 'inline_shapes'):
                                    for shape in run.inline_shapes:
                                        if hasattr(shape, 'image') and hasattr(shape.image, 'rId'):
                                            rId = shape.image.rId
                                            # 记录图片的 element_index（图片应该紧跟当前段落）
                                            image_element_index_map[rId] = element_index
                                            logger.debug(f"[DOCX] 在段落 element_index={element_index} 发现图片 rId={rId}")
                    except Exception as e:
                        logger.debug(f"[DOCX] 检查段落图片失败（可忽略）: {e}")
                    
                    text = (p.text or '').strip()
                    if not text:
                        continue
                    style_name = getattr(getattr(p, 'style', None), 'name', '') or ''
                    is_title = (style_name.startswith('Heading') or 'Title' in style_name)
                    category = 'Title' if is_title else 'NarrativeText'

                    text_content_parts.append(text)
                    filtered_elements_light.append({
                        'category': category,
                        'text': text,
                        'element_index': element_index,
                    })
                    text_element_index_map.append({
                        'element_index': element_index,
                        'element_type': category,
                    })
                    element_index += 1
                else:
                    # 表格
                    t = item
                    cells: List[List[str]] = []
                    try:
                        for r in t.rows:
                            row_vals: List[str] = []
                            for c in r.cells:
                                val = ' '.join((c.text or '').split()).strip()
                                row_vals.append(val)
                            if row_vals:
                                cells.append(row_vals)
                    except Exception as e:
                        logger.warning(f"解析表格失败: {e}")

                    rows = len(cells)
                    cols = len(cells[0]) if rows > 0 else 0
                    table_text = '\n'.join('\t'.join(str(x or '') for x in row) for row in cells) if rows else ''

                    tables.append({
                        'element_index': element_index,
                        'table_data': {
                            'cells': cells,
                            'rows': rows,
                            'columns': cols,
                            'structure': 'docx_extracted',
                            'html': None,
                        },
                        'table_text': table_text,
                        'page_number': None,
                    })

                    filtered_elements_light.append({
                        'category': 'Table',
                        'text': table_text,
                        'element_index': element_index,
                    })
                    element_index += 1
        except Exception as e:
            logger.warning(f"按顺序遍历段落/表格失败，降级为原始遍历（可能顺序不准确）: {e}")
            # 回退：原有逻辑（段落后表格）
            for p in doc.paragraphs:
                text = (p.text or '').strip()
                if not text:
                    continue
                style_name = getattr(getattr(p, 'style', None), 'name', '') or ''
                is_title = (style_name.startswith('Heading') or 'Title' in style_name)
                category = 'Title' if is_title else 'NarrativeText'
                text_content_parts.append(text)
                filtered_elements_light.append({'category': category, 'text': text, 'element_index': element_index})
                text_element_index_map.append({'element_index': element_index, 'element_type': category})
                element_index += 1
            for t in getattr(doc, 'tables', []):
                cells: List[List[str]] = []
                try:
                    for r in t.rows:
                        row_vals: List[str] = []
                        for c in r.cells:
                            val = ' '.join((c.text or '').split()).strip()
                            row_vals.append(val)
                        if row_vals:
                            cells.append(row_vals)
                except Exception:
                    pass
                rows = len(cells)
                cols = len(cells[0]) if rows > 0 else 0
                table_text = '\n'.join('\t'.join(str(x or '') for x in row) for row in cells) if rows else ''
                tables.append({'element_index': element_index, 'table_data': {'cells': cells, 'rows': rows, 'columns': cols, 'structure': 'docx_extracted', 'html': None}, 'table_text': table_text, 'page_number': None})
                filtered_elements_light.append({'category': 'Table', 'text': table_text, 'element_index': element_index})
                element_index += 1

        # 解析图片（关系遍历，并关联 element_index）
        try:
            from docx.opc.constants import RELATIONSHIP_TYPE as RT  # type: ignore
            for rel_id, rel in doc.part.rels.items():
                if "image" in rel.target_ref or rel.reltype in [
                    RT.IMAGE,
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                ]:
                    try:
                        part = rel.target_part
                        data = part.blob
                        if data:
                            # ✅ 从映射中获取图片的 element_index
                            img_element_index = image_element_index_map.get(rel_id)
                            # 如果没找到，使用当前 element_index（图片作为独立元素）
                            if img_element_index is None:
                                img_element_index = element_index
                                element_index += 1
                                logger.debug(f"[DOCX] 图片 rId={rel_id} 未找到关联段落，分配 element_index={img_element_index}")
                            else:
                                logger.debug(f"[DOCX] 图片 rId={rel_id} 关联到 element_index={img_element_index}")
                            
                            images.append({
                                'data': data,
                                'bytes': data,
                                'element_index': img_element_index,  # ✅ 现在有正确的 element_index
                                'page_number': None,
                                'rId': rel_id,  # 保存关系ID用于调试
                            })
                    except Exception as e:
                        logger.warning(f"提取图片失败: {e}")
            
            # ✅ 如果还有未分配的图片（通过其他方式发现的），分配 element_index
            for img in images:
                if img.get('element_index') is None:
                    img['element_index'] = element_index
                    element_index += 1
                    logger.debug(f"[DOCX] 为未关联图片分配 element_index={img['element_index']}")
                    
            logger.info(f"[DOCX] 图片解析完成: 共 {len(images)} 张，element_index 映射: {image_element_index_map}")
        except Exception as e:
            logger.debug(f"图片关系解析失败(可忽略): {e}")

        parse_result: Dict[str, Any] = {
            'text_content': ('\n'.join(text_content_parts)).strip(),
            'tables': tables,
            'images': images,
            'images_binary': [{'binary': im.get('data'), 'element_index': im.get('element_index'), 'page_number': im.get('page_number')} for im in images],
            'text_element_index_map': text_element_index_map,
            'filtered_elements_light': filtered_elements_light,
            'metadata': {
                'element_count': len(filtered_elements_light),
                'filter_stats': {},
                'images_count': len(images),
            },
            'is_converted_pdf': False,
            'converted_pdf_path': None,
        }
        logger.info(f"[DOCX] 解析完成: 元素={len(filtered_elements_light)}, 表格={len(tables)}, 图片={len(images)}")
        return parse_result

    # ============== 分块（复用结构式分块逻辑） ==============
    def chunk_text(
        self,
        text: str,
        text_element_index_map: Optional[Dict[int, Dict[str, Any]]] = None,
        elements: Optional[List[Any]] = None
    ) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        # 若提供 elements，按结构分块
        if elements:
            return self._chunk_by_structure(elements, text_element_index_map)
        # 否则简单段落分块
        chunks: List[Dict[str, Any]] = []
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        for i, para in enumerate(paragraphs):
            chunks.append({
                'content': para,
                'chunk_index': i,
                'element_index_start': None,
                'element_index_end': None,
                'section_id': None,
                'is_parent': False,
            })
        return chunks

    def _chunk_by_structure(
        self,
        elements: List[Any],
        text_element_index_map: Optional[Dict[int, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        # 严格控制单块大小：与 settings 对齐（默认 1000 / 1024）
        try:
            from app.config.settings import settings as _settings
            chunk_max = min(int(getattr(_settings, 'CHUNK_SIZE', 1000)), int(getattr(_settings, 'TEXT_EMBED_MAX_CHARS', 1024)))
        except Exception:
            chunk_max = 1000
        chunks: List[Dict[str, Any]] = []
        current_chunk_texts: List[str] = []
        current_chunk_start: Optional[int] = None
        current_chunk_end: Optional[int] = None
        current_length = 0
        chunk_index = 0
        # 表格不参与文本分块（避免表格文本混入到 text 块导致重复和顺序错乱）
        skip_categories = ['Header', 'Footer', 'PageBreak', 'Table']

        # section/父块标记
        current_section_id = 0
        current_parent_index = None

        def flush_current_chunk():
            nonlocal chunks, current_chunk_texts, current_length, chunk_index, current_chunk_start, current_chunk_end, current_section_id
            if not current_chunk_texts:
                return
            chunk_content = '\n'.join(current_chunk_texts)
            try:
                logger.debug(
                    f"[CHUNK][text] idx={chunk_index} sec={current_section_id} "
                    f"range=({current_chunk_start},{current_chunk_end}) len={len(chunk_content)}"
                )
            except Exception:
                pass
            chunks.append({
                'content': chunk_content,
                'chunk_index': chunk_index,
                'element_index_start': current_chunk_start,
                'element_index_end': current_chunk_end,
                'section_id': current_section_id,
                'is_parent': False,
            })
            chunk_index += 1
            current_chunk_texts = []
            current_length = 0
            current_chunk_start = None
            current_chunk_end = None

        def split_and_append(long_text: str, elem_idx: int):
            """将超长段落按 chunk_max 切分，逐段加入当前 section。
            每一小段的 element_index_start/end 都使用 elem_idx。
            """
            nonlocal current_length, current_chunk_texts, current_chunk_start, current_chunk_end
            logger.debug(f"[SPLIT] elem_idx={elem_idx} long_len={len(long_text)} chunk_max={chunk_max}")
            i = 0
            while i < len(long_text):
                remain = chunk_max - current_length
                if remain <= 0:
                    flush_current_chunk()
                    remain = chunk_max
                take = min(remain, len(long_text) - i)
                piece = long_text[i:i + take]
                if not current_chunk_texts:
                    current_chunk_start = elem_idx
                current_chunk_texts.append(piece)
                current_chunk_end = elem_idx
                current_length += len(piece)
                if current_length >= chunk_max:
                    flush_current_chunk()
                i += take

        last_text_elem_idx: Optional[int] = None
        for element in elements:
            # 兼容 dict / obj 两种元素
            if isinstance(element, dict):
                category = element.get('category', 'NarrativeText')
                text = (element.get('text') or '').strip()
                elem_idx = element.get('element_index')
            else:
                category = getattr(element, 'category', 'NarrativeText')
                text = (getattr(element, 'text', '') or '').strip()
                elem_idx = getattr(element, 'element_index', None)
            if category in skip_categories:
                if category == 'Table':
                    logger.debug(f"[SKIP][table] elem_idx={elem_idx} text_len={len(text)}")
                continue
            if not text:
                continue
            text_length = len(text)
            if category in ['Title', 'ListItem']:
                # 先落当前累积子块（限制在当前 section 内）
                flush_current_chunk()
                # 新的父块（标题）
                current_section_id += 1
                logger.debug(f"[PARENT] idx={chunk_index} sec={current_section_id} elem_idx={elem_idx} len={len(text)}")
                chunks.append({
                    'content': text,
                    'chunk_index': chunk_index,
                    'element_index_start': elem_idx,
                    'element_index_end': elem_idx,
                    'section_id': current_section_id,
                    'is_parent': True,
                })
                current_parent_index = chunk_index
                chunk_index += 1
                # 重置累积器
                current_chunk_texts = []
                current_length = 0
                current_chunk_start = None
                current_chunk_end = None
            else:
                # 若与上一个文本元素不相邻（中间夹了表格或其他元素），先切断
                if last_text_elem_idx is not None and elem_idx is not None and current_chunk_texts:
                    if elem_idx != (current_chunk_end if current_chunk_end is not None else last_text_elem_idx) + 1:
                        logger.debug(f"[BOUNDARY] flush by gap: prev={last_text_elem_idx} current={elem_idx}")
                        flush_current_chunk()

                if text_length > chunk_max:
                    split_and_append(text, elem_idx)
                else:
                    # 正常累积，必要时先换新块
                    if current_length + text_length > chunk_max:
                        flush_current_chunk()
                    if not current_chunk_texts:
                        current_chunk_start = elem_idx
                    current_chunk_texts.append(text)
                    current_chunk_end = elem_idx
                    current_length += text_length
                last_text_elem_idx = elem_idx if elem_idx is not None else last_text_elem_idx
        # 收尾：仅在当前 section 内 flush，不做全文聚合
        flush_current_chunk()
        logger.info(f"[DOCX] 结构分块完成，共 {len(chunks)} 个分块（section_id 最大为 {current_section_id}，chunk_max={chunk_max}）")
        try:
            # 打印每个块的概览，便于定位错位/重复
            for c in chunks:
                logger.debug(
                    f"[CHUNK_SUMMARY] idx={c.get('chunk_index')} sec={c.get('section_id')} "
                    f"range=({c.get('element_index_start')},{c.get('element_index_end')}) "
                    f"len={len(c.get('content') or '')}"
                )
        except Exception:
            pass
        return chunks
