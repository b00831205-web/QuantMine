from pathlib import Path
from dataclasses import dataclass
from ..storage.connections import ConnectionRegistry

@dataclass
class SourceContext:
    connections: ConnectionRegistry #连接注册表
    run_id: int #当前研究运行
    artifact_dir: Path #产物目录