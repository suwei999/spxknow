"""
Diff Analysis Service
根据文档修改功能设计实现差异计算和版本比较功能
"""

import difflib
from typing import Dict, Any, List, Tuple
from datetime import datetime
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode


class DiffAnalysisService:
    """差异分析服务 - 根据设计文档实现"""
    
    def __init__(self):
        self.RISK_ASSESSMENT_THRESHOLDS = {
            "high_change_ratio": 0.5,    # 修改比例超过50%为高风险
            "large_content_deletion": 1000,  # 删除超过1000字符为高风险
            "structural_change": True     # 结构性变化为高风险
        }
    
    def calculate_content_diff(
        self,
        old_content: str,
        new_content: str
    ) -> Dict[str, Any]:
        """计算内容差异 - 根据设计文档实现"""
        try:
            logger.info("开始计算内容差异")
            
            # 使用Python difflib计算差异
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            
            # 计算差异
            diff = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile='旧版本',
                tofile='新版本',
                lineterm=''
            ))
            
            # 统计差异
            added_lines = 0
            removed_lines = 0
            modified_lines = 0
            
            for line in diff:
                if line.startswith('+') and not line.startswith('+++'):
                    added_lines += 1
                elif line.startswith('-') and not line.startswith('---'):
                    removed_lines += 1
            
            # 修改行数 = 同时有增加和删除的块
            total_diff_blocks = len([l for l in diff if l.startswith('@@')])
            
            # 计算总体变化
            total_changes = added_lines + removed_lines
            
            return {
                "added_lines": added_lines,
                "removed_lines": removed_lines,
                "modified_lines": total_diff_blocks,
                "total_changes": total_changes,
                "change_ratio": total_changes / len(old_lines) if len(old_lines) > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"计算内容差异失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"计算内容差异失败: {str(e)}"
            )
    
    def calculate_similarity_score(
        self,
        content1: str,
        content2: str
    ) -> float:
        """计算相似度分数 - 根据设计文档实现"""
        try:
            logger.info("开始计算相似度")
            
            # 使用difflib.SequenceMatcher计算相似度
            matcher = difflib.SequenceMatcher(None, content1, content2)
            similarity = matcher.ratio()
            
            logger.info(f"相似度计算完成: {similarity:.4f}")
            return similarity
            
        except Exception as e:
            logger.error(f"计算相似度失败: {e}", exc_info=True)
            return 0.0
    
    def assess_risk(self, diff_result: Dict[str, Any]) -> str:
        """评估修改风险 - 根据设计文档实现"""
        try:
            logger.info("开始评估修改风险")
            
            change_ratio = diff_result.get("change_ratio", 0)
            total_changes = diff_result.get("total_changes", 0)
            removed_lines = diff_result.get("removed_lines", 0)
            
            # 风险等级判断
            if change_ratio >= self.RISK_ASSESSMENT_THRESHOLDS["high_change_ratio"]:
                return "high"  # 高风险：修改比例超过50%
            elif total_changes >= self.RISK_ASSESSMENT_THRESHOLDS["large_content_deletion"]:
                return "high"  # 高风险：修改量很大
            elif removed_lines > 100:
                return "medium"  # 中等风险：删除内容较多
            elif total_changes > 50:
                return "medium"  # 中等风险：修改量较大
            else:
                return "low"  # 低风险：少量修改
                
        except Exception as e:
            logger.error(f"评估风险失败: {e}", exc_info=True)
            return "unknown"
    
    def estimate_processing_time(
        self,
        content_length: int,
        similarity_score: float
    ) -> str:
        """预估处理时间 - 根据设计文档实现"""
        try:
            logger.info("开始预估处理时间")
            
            # 基础处理时间（秒）
            base_time = 10
            
            # 根据内容长度调整
            length_factor = content_length / 1000  # 每1000字符增加1秒
            
            # 根据相似度调整（修改幅度越大，时间越长）
            similarity_factor = (1 - similarity_score) * 30  # 相似度越低，时间越长
            
            # 计算总时间
            total_seconds = base_time + length_factor + similarity_factor
            
            # 格式化时间
            if total_seconds < 60:
                return f"{int(total_seconds)}s"
            elif total_seconds < 3600:
                minutes = int(total_seconds / 60)
                return f"{minutes}m"
            else:
                hours = int(total_seconds / 3600)
                return f"{hours}h"
                
        except Exception as e:
            logger.error(f"预估时间失败: {e}", exc_info=True)
            return "30s"  # 默认时间
    
    def compare_versions(
        self,
        version1_content: str,
        version2_content: str
    ) -> Dict[str, Any]:
        """比较两个版本 - 根据设计文档实现"""
        try:
            logger.info("开始版本比较")
            
            # 计算差异
            diff_result = self.calculate_content_diff(version1_content, version2_content)
            
            # 计算相似度
            similarity_score = self.calculate_similarity_score(version1_content, version2_content)
            
            return {
                "added_lines": diff_result["added_lines"],
                "removed_lines": diff_result["removed_lines"],
                "modified_lines": diff_result["modified_lines"],
                "total_changes": diff_result["total_changes"],
                "similarity_score": similarity_score,
                "change_ratio": diff_result["change_ratio"]
            }
            
        except Exception as e:
            logger.error(f"版本比较失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"版本比较失败: {str(e)}"
            )

