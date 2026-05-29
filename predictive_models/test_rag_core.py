"""Quick unit checks for RAG parsing helpers."""

from predictive_models.rag_core import (
    hierarchical_baseline_log10,
    parse_first_float,
    parse_predictions_json,
    species_anchor_log10,
)


def main() -> None:
    assert parse_predictions_json('{"predictions": [1.5, 2.0]}', 2) == [1.5, 2.0]
    assert parse_predictions_json('```json\n{"predictions": [1.5, 2.0]}\n```', 2) == [1.5, 2.0]
    assert parse_predictions_json('Here is the result:\n{"predictions": [3.14]}', 1) == [3.14]
    assert parse_first_float("The answer is 3.14 grams") == 3.14

    query = {"kingdom": "Animalia", "phylum": "X", "class": "Y", "order": "O", "family": "F", "genus": "G", "species": "G foo"}
    retrieved = [
        (query, 100.0, 2.0, 0.95),
        ({"kingdom": "Animalia", "phylum": "X", "class": "Y", "order": "O", "family": "F", "genus": "H", "species": "H bar"}, 1000.0, 3.0, 0.5),
    ]
    assert species_anchor_log10(query, retrieved) == 2.0
    assert hierarchical_baseline_log10(query, retrieved) == 2.0

    print("rag_core parsing tests: OK")


if __name__ == "__main__":
    main()
