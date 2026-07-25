"""Identity builder tests."""

from magnet.resource_index.domain.enums import ContentType, MediaType
from magnet.resource_index.domain.identity import (
    content_id_for,
    media_id_for,
    person_id_for,
    resource_id_for,
    tag_id_for,
)
from magnet.resource_index.errors import ValidationError
import pytest


def test_content_id_stable():
    assert content_id_for(ContentType.ADULT_VIDEO, "tst-001") == "adult_video:TST-001"
    assert content_id_for(ContentType.ADULT_VIDEO, "TST-001") == "adult_video:TST-001"


def test_person_id_prefers_slug():
    assert (
        person_id_for(slug="person-one", display_name="X", source_prefix="javbus")
        == "javbus:person:person-one"
    )


def test_person_id_name_hash_stable():
    a = person_id_for(slug=None, display_name="Fixture Person", source_prefix="site")
    b = person_id_for(slug=None, display_name="Fixture Person", source_prefix="site")
    c = person_id_for(slug=None, display_name="Other", source_prefix="site")
    assert a == b
    assert a != c
    assert a.startswith("name:")


def test_tag_id_external_key():
    assert (
        tag_id_for(external_key="tag-a", display_name="A", source_prefix="javbus")
        == "javbus:tag:tag-a"
    )


def test_resource_id_requires_hex40():
    rid = resource_id_for("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA".lower())
    assert rid == "btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    with pytest.raises(ValidationError):
        resource_id_for("short")


def test_media_id_deterministic():
    m1 = media_id_for("adult_video:TST-001", MediaType.COVER, "https://x/y.jpg")
    m2 = media_id_for("adult_video:TST-001", MediaType.COVER, "https://x/y.jpg")
    assert m1 == m2
