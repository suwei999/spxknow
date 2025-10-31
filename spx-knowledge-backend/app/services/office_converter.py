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


def compress_pdf(input_pdf: str, output_pdf: str, quality: str = "screen") -> bool:
    """使用 Ghostscript 压缩 PDF。quality 可选: screen, ebook, printer, prepress.
    返回 True 表示成功，False 表示失败或未安装 gs。
    """
    try:
        gs = getattr(settings, 'GS_PATH', 'gs')
        cmd = [
            gs,
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            f'-dPDFSETTINGS=/{quality}',
            '-dNOPAUSE',
            '-dBATCH',
            '-dQUIET',
            f'-sOutputFile={output_pdf}',
            input_pdf,
        ]
        logger.info(f"[Ghostscript] 压缩PDF: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.warning(f"[Ghostscript] 压缩失败 rc={result.returncode} stderr={result.stderr[:200] if result.stderr else ''}")
            return False
        return True
    except FileNotFoundError:
        logger.warning("[Ghostscript] 未安装或GS_PATH无效，跳过PDF压缩")
        return False
    except Exception as e:
        logger.warning(f"[Ghostscript] 压缩异常: {e}")
        return False

