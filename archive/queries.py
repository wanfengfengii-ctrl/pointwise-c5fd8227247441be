from archive.revisions import Revision, RevisionRef, RevisionStore


def get_revision(store: RevisionStore, ref: RevisionRef) -> Revision | None:
    if not isinstance(ref, RevisionRef):
        raise ValueError('查询须指定确切修订')
    return store.read_exact(ref)


def get_current_revision(store: RevisionStore, batch: str) -> Revision | None:
    return store.read_current(batch)
