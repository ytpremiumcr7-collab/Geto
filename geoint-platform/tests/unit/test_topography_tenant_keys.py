import pytest

from app.topography.service import derived_object_key


def test_derived_object_key_is_tenant_scoped():
    a = derived_object_key("tenant-a", "slope", "dem-1_slope.tif")
    b = derived_object_key("tenant-b", "slope", "dem-1_slope.tif")

    assert a == "derived/tenant-a/slope/dem-1_slope.tif"
    assert b == "derived/tenant-b/slope/dem-1_slope.tif"
    assert a != b


@pytest.mark.parametrize("tenant_id", ["", ".", "..", "../tenant-b", "tenant/a", "tenant\\a"])
def test_derived_object_key_rejects_unsafe_tenant_segments(tenant_id):
    with pytest.raises(ValueError, match="unsafe derived object key component"):
        derived_object_key(tenant_id, "slope", "dem-1_slope.tif")
