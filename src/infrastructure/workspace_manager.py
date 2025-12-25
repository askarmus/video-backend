import shutil
import tempfile
from pathlib import Path
from src.config import TEMP_DIR

class LocalWorkspace:
    """
    Context manager for handling temporary workspaces.
    Encapsulates path creation and auto-cleanup.
    """
    def __init__(self, prefix: str = "workspace_"):
        self.prefix = prefix
        self.path: Path = None

    def __enter__(self):
        # Create a unique temp folder inside our app's standard TEMP_DIR
        tmp_path = tempfile.mkdtemp(prefix=self.prefix, dir=str(TEMP_DIR))
        self.path = Path(tmp_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.path and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)

    def create_dir(self, name: str) -> Path:
        """Helper to create a subdirectory in the workspace"""
        new_dir = self.path / name
        new_dir.mkdir(parents=True, exist_ok=True)
        return new_dir

    def get_path(self, *parts: str) -> str:
        """Returns a string path for tools that don't support Path objects yet"""
        return str(self.path.joinpath(*parts))
