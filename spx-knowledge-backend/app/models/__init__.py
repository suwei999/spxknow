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
from app.models.cluster_config import ClusterConfig  # noqa: F401
from app.models.resource_snapshot import ResourceSnapshot  # noqa: F401
from app.models.diagnosis_record import DiagnosisRecord  # noqa: F401
from app.models.diagnosis_iteration import DiagnosisIteration  # noqa: F401
from app.models.diagnosis_memory import DiagnosisMemory  # noqa: F401
from app.models.resource_event import ResourceEvent  # noqa: F401
from app.models.resource_sync_state import ResourceSyncState  # noqa: F401
