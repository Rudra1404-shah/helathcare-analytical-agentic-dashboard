"""Guards on the test harness itself and on the model registry."""

import pytest
from beanie.odm.utils.init import Initializer

from src.domain.models import ALL_DOCUMENT_MODELS
from tests import factories

EXPECTED_COLLECTIONS = {
    "users",
    "zones",
    "hospitals",
    "departments",
    "staff",
    "doctors",
    "patients",
    "case_types",
    "patient_cases",
    "hospital_inventory",
    "bills",
    "complaints",
}


def test_document_registry_is_live() -> None:
    """Documents must be constructible, proving the conftest bootstrap worked.

    If this fails with ``CollectionWasNotInitialized``, a Beanie upgrade has
    changed the initialisation path that ``tests/conftest.py`` stubs.
    """
    # Arrange / Act
    hospital = factories.build_hospital()

    # Assert
    assert hospital.name == "Test General Hospital"


def test_beanie_internal_stubbed_by_conftest_still_exists() -> None:
    """The internal the conftest patches must still be present in Beanie."""
    assert hasattr(Initializer, "_load_cached_info"), (
        "Beanie removed Initializer._load_cached_info; tests/conftest.py needs updating"
    )


def test_all_twelve_collections_are_registered() -> None:
    """Every planned collection must be in the Beanie registry."""
    # Act
    registered = {model.Settings.name for model in ALL_DOCUMENT_MODELS}  # type: ignore[attr-defined]

    # Assert
    assert registered == EXPECTED_COLLECTIONS
    assert len(ALL_DOCUMENT_MODELS) == 12


@pytest.mark.parametrize("model", ALL_DOCUMENT_MODELS, ids=lambda m: m.__name__)
def test_every_model_declares_a_collection_name(model: type) -> None:
    """A model without an explicit collection name would silently use its class name."""
    settings = getattr(model, "Settings", None)
    assert settings is not None, f"{model.__name__} has no Settings class"
    assert getattr(settings, "name", None), f"{model.__name__} declares no collection name"


@pytest.mark.parametrize("model", ALL_DOCUMENT_MODELS, ids=lambda m: m.__name__)
def test_every_model_carries_timestamps(model: type) -> None:
    """Analytics depends on every record having created_at and updated_at."""
    fields = model.model_fields  # type: ignore[attr-defined]
    assert "created_at" in fields
    assert "updated_at" in fields
