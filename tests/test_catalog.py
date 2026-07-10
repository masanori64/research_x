from research_x.adapters import catalog_entries, known_adapter_ids
from research_x.adapters.catalog import get_catalog_entry


def test_catalog_covers_all_known_adapters() -> None:
    catalog_ids = {entry.adapter_id for entry in catalog_entries()}

    assert catalog_ids == set(known_adapter_ids())


def test_catalog_prioritizes_x_specific_adapters() -> None:
    entries = catalog_entries()
    priorities = {entry.adapter_id: entry.priority for entry in entries}

    assert priorities["twscrape_raw"] < priorities["playwright"]
    assert get_catalog_entry("scweet").acquisition_layer == "x_internal_graphql"
