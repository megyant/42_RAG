from .ingesting import Ingest


class Manager:
    def __init__(self):
        self.dataset_path = "data/raw"

    def ingestion(self):
        ingest = Ingest(self.dataset_path)
        files = ingest.collect_files()
        # print(files)
        for file in files:
            ingest.read_file(file)
