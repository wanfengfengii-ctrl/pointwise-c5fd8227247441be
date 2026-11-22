from archive.revisions import RevisionRef, RevisionStore


class BatchArchive:
    def __init__(self, store: RevisionStore):
        self.store = store

    def submit(self, batch: str, observations, scenario_inputs=()) -> RevisionRef:
        return self.store.append(batch, observations, scenario_inputs)

    def correct(self, parent: RevisionRef, observations, scenario_inputs=()) -> RevisionRef:
        if not isinstance(parent, RevisionRef):
            raise ValueError('勘误须指定确切父修订')
        return self.store.append(parent.batch, observations, scenario_inputs, parent=parent.number)
