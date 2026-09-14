from app.infrastructure.object_store import ObjectStore


def test_make_key_includes_tenant_and_is_unique():
    # avoid needing minio client fully — only exercise make_key
    class T(ObjectStore):
        def __init__(self):
            pass

    store = T()
    k1 = store.make_key("firms", tenant_id="tA", job_id="j1", message_id="m1")
    k2 = store.make_key("firms", tenant_id="tB", job_id="j1", message_id="m1")
    k3 = store.make_key("firms", tenant_id="tA", job_id="j1", message_id="m2")
    assert k1.startswith("raw/tA/firms/")
    assert k2.startswith("raw/tB/firms/")
    assert k1 != k2
    assert k1 != k3
