import subprocess
import tempfile
import os
from typing import Optional
from app.core.logging import logger
from app.config.settings import settings


def convert_docx_to_pdf(input_path: str) -> Optional[str]:
    """使用 LibreOffice 将 DOCX 转为 PDF，成功返回输出路径，失败返回 None。"""
    try:
        if not os.path.exists(input_path):
            logger.error(f"LibreOffice 转换失败，文件不存在: {input_path}")
            return None
        out_dir = tempfile.mkdtemp(prefix="soffice_pdf_")
        cmd = [
            settings.SOFFICE_PATH,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--nofirststartwizard",
            "--convert-to",
            "pdf",
            "--outdir",
            out_dir,
            input_path,
        ]
        logger.info(f"[LibreOffice] 执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        logger.info(f"[LibreOffice] returncode={result.returncode}")
        if result.stdout:
            logger.info(f"[LibreOffice][stdout]\n{result.stdout}")
        if result.stderr:
            logger.warning(f"[LibreOffice][stderr]\n{result.stderr}")
        if result.returncode != 0:
            logger.error(f"[LibreOffice] 转换失败: rc={result.returncode}")
            return None
        base = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(out_dir, f"{base}.pdf")
        if not os.path.exists(output_path):
            logger.error("LibreOffice 转换后未找到输出 PDF")
            return None
        logger.info(f"[LibreOffice] 转换成功: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"[LibreOffice] 转换异常: {e}")
        return None


