# Models package
# Ensure all model modules are imported so that SQLAlchemy can resolve string-based relationships
from app.models.knowledge_base import KnowledgeBase  # noqa: F401
from app.models.knowledge_base_category import KnowledgeBaseCategory  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.chunk import DocumentChunk  # noqa: F401
from app.models.chunk_version import ChunkVersion  # noqa: F401
from app.models.version import DocumentVersion  # noqa: F401
from app.models.image import DocumentImage  # noqa: F401
from app.models.qa_session import QASession  # noqa: F401
from app.models.qa_question import QAQuestion, QAStatistics  # noqa: F401
from app.models.system import SystemConfig, OperationLog  # noqa: F401
from app.models.task import CeleryTask  # noqa: F401
