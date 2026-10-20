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
    "model.ubj": "6bad674b79ccab14ed721c311ad47349f0530a7fddc3f3cb25fdf2b025fa5dbd",  # noqa: E501
    "calibration.json": "890527f72e80b25d93d15e136c9ee7b9fe424113770743e0f800b8f8f08b8ff9",  # noqa: E501
    "calibration_by_rank.json": "73f933218adb4353f3812d6f97e092945aabecb938d39e40db167895b1ab5aa0",  # noqa: E501
    "categories.json": "f9495c6f6b9c4411512f8083faed0e40bcffe548b1bf12e7b9f7656382df9218",  # noqa: E501
    "lookup.json": "e49b971caa4d7b9078a59a0681a8cb9cde78e67f4244bc0e3c689eaf43255784",  # noqa: E501
    # Entity Embeddings
    "embeddings.json": "9abc38faff6ac490f27480d1c19698c19d8e3a934acd76919c95bf366ac8ec17",  # noqa: E501
    "model_ee.ubj": "9b27e77101ee5559e8e58e8d1ebbbea4ee23b92606ce9c7ff2025a8b522f2eb6",  # noqa: E501
    "calibration_ee.json": "cd68beb482bc1427e7163f0665260ef2a13b9dd47e6f353bac46172aa1519200",  # noqa: E501
    "calibration_by_rank_ee.json": "1c12da9c75e261240ff34867e99081277c62744f20ef432748a86d5dc3268083",  # noqa: E501
}

# Provenance artifacts (TaxonBodyMass_DB issue #1): the generated primary-source
# bibliography and the species x source x reference provenance table, built from
# the same TaxonBodyMass_DB snapshot as lookup.json. Downloaded by
# download_model() together with the model artifacts, and on first use by
# get_citations(level="primary") / create_bib(level="primary"). predict_mass()
# does not need them.
PROVENANCE_CHECKSUMS = {
    "PrimaryCitations_BodyMass.bib": "a2e9490cd37cc020e4d76d30f1362344a934870b093795896879960784b2d71f",  # noqa: E501
    "TaxonBodyMass_Provenance.csv.gz": "cfd931c8431061859e97a80581691a85324845e51b1da45d8c22ed6e20d1ce49",  # noqa: E501
}
