from pathlib import Path
def list_datasets():
    data_dir = Path("data/raw")
    return [f.name for f in data_dir.glob("*") if f.is_file()]
