import yaml
from pathlib import Path
from typing import TypeVar, Type
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

def load_yaml_config(file_path: str | Path, model_class: Type[T]) -> T:
    """
    Loads a YAML file and parses it into the provided Pydantic model.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
        
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
        
    return model_class.model_validate(data)
