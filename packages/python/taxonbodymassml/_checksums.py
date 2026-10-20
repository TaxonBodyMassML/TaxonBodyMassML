# Auto-generated constants — do not edit by hand.
# CHECKSUMS, PROVENANCE_CHECKSUMS and MODEL_ARTIFACT_VERSION are updated by
# scripts/sync_checksums.py / scripts/publish_artifacts.py when new artifacts
# are uploaded to HuggingFace. They are intentionally independent of the
# package version so that code-only releases do not require a new HuggingFace
# upload.
HF_REPO_ID = "marknovak/TaxonBodyMassML"

# HuggingFace revision that hosts the current model artifacts (py-v<version>).
# Only advances when make publish is run with new artifacts.
MODEL_ARTIFACT_VERSION = "0.13.0"

# Model artifacts: required by predict_mass() and downloaded on first use.
CHECKSUMS = {
    # XGBoost (original method)
    "model.ubj": "8d4364a5f6451ccc457392faa80e761ede0c6ab7f58fdd34b49cca6df30f5e23",  # noqa: E501
    "calibration.json": "4903078978c6aa1432dfbddbf46fe67ef6839cca5baa6395f070bf4536c5e6bb",  # noqa: E501
    "calibration_by_rank.json": "ccd5d4f29606174038c1ac8d62d91395eb909257dfd1eb6478bb72926c6740e7",  # noqa: E501
    "categories.json": "6cd53c20b129ace0be8d3546487174caffc095242794d6f4452e3dd827e2708c",  # noqa: E501
    "lookup.json": "4a1c0b037556f499c4264bf8cd6d5005ef3bf1a96c4e859236afad7074970570",  # noqa: E501
    # Entity Embeddings
    "embeddings.json": "b6c5bec4334653c247353054da1ad75592cf6bc6e146d07cb5a5f5cb575062cd",  # noqa: E501
    "model_ee.ubj": "de95816c6184d2a7979136c700ce91bdaa41974fc6f8927bb294bcad9693452a",  # noqa: E501
    "calibration_ee.json": "2abbf251382e08e283f49aaf3a3681e03d554df82ecd576d36e264a831ff0bae",  # noqa: E501
    "calibration_by_rank_ee.json": "43f21b33c208166afafd2a6c8d3d3ddc8b9dab1520231de6324d53ee9ca05e86",  # noqa: E501
}

# Provenance artifacts (TaxonBodyMass_DB issue #1): the generated primary-source
# bibliography and the species x source x reference provenance table, built from
# the same TaxonBodyMass_DB snapshot as lookup.json. Downloaded by
# download_model() together with the model artifacts, and on first use by
# get_citations(level="primary") / create_bib(level="primary"). predict_mass()
# does not need them.
PROVENANCE_CHECKSUMS = {
    "PrimaryCitations_BodyMass.bib": "bfef580ef0be5c139186b3d68a0bd1c262d34646940be6a3e3ed3248f47da8ef",  # noqa: E501
    "TaxonBodyMass_Provenance.csv.gz": "9e6e76bc4fb0691ddd660367074ce548c87743959f6bd8a5ef8eeb06bc79eaee",  # noqa: E501
}
