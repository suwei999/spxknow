from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.logging import logger
from app.models.chunk import DocumentChunk


class QueryService:
    """
    查询聚合服务：对命中的 chunk 做上下文聚合（父子+邻接窗口），并返回表格/图片上下文。
    仅依赖 DB 的 chunks 表（content/meta）与 element_index 相关元信息。
    """

    def __init__(self, db: Session):
        self.db = db

    def get_context_for_hit(
        self,
        document_id: int,
        hit_chunk_id: int,
        neighbor_pre: int = 1,
        neighbor_next: int = 1,
        parent_group_max_chars: int = 1500,
        total_context_max_chars: int = 2500,
        max_tables: int = 2,
        max_images: int = 2,
    ) -> Dict[str, Any]:
        chunk: Optional[DocumentChunk] = self.db.query(DocumentChunk).filter(
            DocumentChunk.id == hit_chunk_id,
            DocumentChunk.document_id == document_id,
            DocumentChunk.is_deleted == False,
        ).first()
        if not chunk:
            return {"error": "chunk_not_found"}

        # 取同文档全部块（按 chunk_index）
        all_chunks: List[DocumentChunk] = self.db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.is_deleted == False,
        ).order_by(DocumentChunk.chunk_index).all()

        # 解析 meta
        import json
        def load_meta(raw):
            if not raw:
                return {}
            if isinstance(raw, dict):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return {}

        hit_meta = load_meta(chunk.meta)
        section_id = hit_meta.get('section_id')
        parent_chunk_id = hit_meta.get('parent_chunk_id')

        # 父子聚合
        siblings: List[Dict[str, Any]] = []
        if parent_chunk_id is not None:
            for c in all_chunks:
                cm = load_meta(c.meta)
                if cm.get('parent_chunk_id') == parent_chunk_id:
                    siblings.append({
                        'chunk_id': c.id,
                        'chunk_index': c.chunk_index,
                        'content': c.content or "",
                        'chunk_type': getattr(c, 'chunk_type', 'text'),
                    })
            siblings.sort(key=lambda x: x.get('chunk_index', 0))

        # 邻接窗口
        neighbors_prev: List[Dict[str, Any]] = []
        neighbors_next_list: List[Dict[str, Any]] = []
        hit_pos = next((i for i, c in enumerate(all_chunks) if c.id == hit_chunk_id), -1)
        if hit_pos >= 0:
            i = hit_pos - 1
            cnt = 0
            while i >= 0 and cnt < neighbor_pre:
                cm = load_meta(all_chunks[i].meta)
                if section_id is None or cm.get('section_id') == section_id:
                    neighbors_prev.append({
                        'chunk_id': all_chunks[i].id,
                        'chunk_index': all_chunks[i].chunk_index,
                        'content': all_chunks[i].content or "",
                        'chunk_type': getattr(all_chunks[i], 'chunk_type', 'text'),
                    })
                    cnt += 1
                i -= 1
            neighbors_prev.reverse()
            j = hit_pos + 1
            cnt = 0
            while j < len(all_chunks) and cnt < neighbor_next:
                cm = load_meta(all_chunks[j].meta)
                if section_id is None or cm.get('section_id') == section_id:
                    neighbors_next_list.append({
                        'chunk_id': all_chunks[j].id,
                        'chunk_index': all_chunks[j].chunk_index,
                        'content': all_chunks[j].content or "",
                        'chunk_type': getattr(all_chunks[j], 'chunk_type', 'text'),
                    })
                    cnt += 1
                j += 1

        # 组装 merged_text（父子优先）并做总长度限制
        merged_parts: List[str] = []
        if siblings:
            total = 0
            for s in siblings:
                txt = s.get('content') or ""
                if not txt:
                    continue
                if total + len(txt) > parent_group_max_chars:
                    break
                merged_parts.append(txt)
                total += len(txt)
        else:
            merged_parts.extend([*(x.get('content') or "" for x in neighbors_prev), chunk.content or "", *(x.get('content') or "" for x in neighbors_next_list)])
        merged_text = "\n".join([p for p in merged_parts if p])
        if len(merged_text) > total_context_max_chars:
            merged_text = merged_text[:total_context_max_chars]

        # 附带邻接中的表格/图片（数量限制）
        def pick_nontext_limited(items: List[Dict[str, Any]], mt: int, mi: int):
            tables: List[Dict[str, Any]] = []
            images: List[Dict[str, Any]] = []
            for it in items:
                if it.get('chunk_type') == 'table' and len(tables) < mt:
                    tables.append({'chunk_id': it['chunk_id']})
                elif it.get('chunk_type') == 'image' and len(images) < mi:
                    images.append({'chunk_id': it['chunk_id']})
            return tables, images

        t_prev, i_prev = pick_nontext_limited(neighbors_prev, max_tables, max_images)
        t_next, i_next = pick_nontext_limited(neighbors_next_list, max_tables - len(t_prev), max_images - len(i_prev))

        # 如果命中表块，补充整表 JSON（支持分片聚合）
        tables_payload: List[Dict[str, Any]] = []
        if getattr(chunk, 'chunk_type', 'text') == 'table':
            import json
            hit_table_meta = hit_meta
            table_uid = hit_table_meta.get('table_id')
            table_group_uid = hit_table_meta.get('table_group_uid')
            try:
                if table_group_uid:
                    sql = text(
                        "SELECT table_uid, headers_json, cells_json, part_index FROM document_tables "
                        "WHERE document_id=:document_id AND table_group_uid=:table_group_uid ORDER BY part_index ASC"
                    )
                    rows = self.db.execute(sql, {"document_id": document_id, "table_group_uid": table_group_uid}).fetchall()
                    headers = None
                    cells: List[List[str]] = []
                    for r in rows:
                        _, h, c, _ = r
                        try:
                            if headers is None and h:
                                headers = json.loads(h) if isinstance(h, str) else h
                        except Exception:
                            headers = headers or {}
                        try:
                            part_cells = json.loads(c) if isinstance(c, str) else (c or [])
                        except Exception:
                            part_cells = []
                        if isinstance(part_cells, list):
                            cells.extend([[str(x) if x is not None else "" for x in row] if isinstance(row, list) else [str(row)] for row in part_cells])
                    tables_payload.append({
                        'table_id': table_group_uid,
                        'json': {'headers': headers or {}, 'cells': cells},
                    })
                elif table_uid:
                    sql = text(
                        "SELECT headers_json, cells_json FROM document_tables WHERE document_id=:document_id AND table_uid=:table_uid LIMIT 1"
                    )
                    r = self.db.execute(sql, {"document_id": document_id, "table_uid": table_uid}).fetchone()
                    if r:
                        h, c = r
                        try:
                            headers = json.loads(h) if isinstance(h, str) else (h or {})
                        except Exception:
                            headers = {}
                        try:
                            cells = json.loads(c) if isinstance(c, str) else (c or [])
                        except Exception:
                            cells = []
                        tables_payload.append({'table_id': table_uid, 'json': {'headers': headers, 'cells': cells}})
            except Exception as e:
                logger.warning(f"QueryService: 聚合表格失败: {e}")

        result: Dict[str, Any] = {
            'hit': {
                'chunk_id': chunk.id,
                'type': getattr(chunk, 'chunk_type', 'text'),
                'score': None,  # 预留：排序融合权重
            },
            'context': {
                'parent': None if parent_chunk_id is None else {'parent_chunk_id': parent_chunk_id},
                'siblings': siblings,
                'neighbors': {
                    'prev': neighbors_prev,
                    'next': neighbors_next_list,
                },
                'tables': tables_payload or (t_prev + t_next),
                'images': i_prev + i_next,
            },
            'display': {
                'merged_text': merged_text,
                'render_hint': 'text' if getattr(chunk, 'chunk_type', 'text') == 'text' else 'mixed',
            }
        }
        return result
