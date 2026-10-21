# Auto-generated constants — do not edit by hand.
# CHECKSUMS, PROVENANCE_CHECKSUMS and MODEL_ARTIFACT_VERSION are updated by
# scripts/sync_checksums.py / scripts/publish_artifacts.py when new artifacts
# are uploaded to HuggingFace. They are intentionally independent of the
# package version so that code-only releases do not require a new HuggingFace
# upload.
HF_REPO_ID = "marknovak/TaxonBodyMassML"

# HuggingFace revision that hosts the current model artifacts (py-v<version>).
# Only advances when make publish is run with new artifacts.
MODEL_ARTIFACT_VERSION = "0.14.0"

# Model artifacts: required by predict_mass() and downloaded on first use.
CHECKSUMS = {
    # XGBoost (original method)
    "model.ubj": "d6bdf11be39edd9c660674dbf61e218cf08d057ff0c5b8d84e494b99a0a1a2de",  # noqa: E501
    "calibration.json": "db1910a0c494fbee79427be205a30b1369a0594598c57fcc853d71106a5fac1d",  # noqa: E501
    "calibration_by_rank.json": "fdb373b3efa75a0b809370e551bf218e892768e333011c36552a02c92e277a47",  # noqa: E501
    "categories.json": "39cf2745b3d96453770b536116d8bcb3cbca73fa95ac56b2a70da700a68ea90a",  # noqa: E501
    "lookup.json": "4a1c0b037556f499c4264bf8cd6d5005ef3bf1a96c4e859236afad7074970570",  # noqa: E501
    # Entity Embeddings
    "embeddings.json": "a378cb233b103d950c4e91c0b408810ceb31a188372679d768dd7c71bbe5fa42",  # noqa: E501
    "model_ee.ubj": "57f062da07887446d026ca357e2fcafcb0c2d3ab4c3bc34f9a1642f3f9e5acb7",  # noqa: E501
    "calibration_ee.json": "0a0e92c8ccef39fdfad07613dff5e39745ff307a3e4bcb707f85b5d93defb6ac",  # noqa: E501
    "calibration_by_rank_ee.json": "723be598d80bb62033f4b26e219006cc72ea8ab3af8d38b7810901381471d3d5",  # noqa: E501
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
