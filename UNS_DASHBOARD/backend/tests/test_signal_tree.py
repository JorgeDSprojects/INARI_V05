from app.services.signal_tree import build_tree, topic_type_of


def test_topic_type_of_matches_informative_and_analytical():
    assert topic_type_of("a/b/_informative") == "informative"
    assert topic_type_of("a/b/_analytical") == "analytical"


def test_topic_type_of_returns_none_for_descriptive_and_unsuffixed():
    assert topic_type_of("a/b/_descriptive") is None
    assert topic_type_of("a/b") is None


def test_build_tree_nests_by_path_segment():
    tree = build_tree([("Planta1/Linea3/_informative", "informative", ["Gen_RPM_Avg"])])
    assert tree == [{
        "segment": "Planta1",
        "children": [{
            "segment": "Linea3",
            "children": [{
                "segment": "_informative",
                "children": [],
                "leaf": {"topic": "Planta1/Linea3/_informative", "topic_type": "informative", "keys": ["Gen_RPM_Avg"]},
            }],
        }],
    }]


def test_build_tree_merges_shared_prefixes_and_sorts_children():
    tree = build_tree([
        ("Planta1/L2/_informative", "informative", ["B"]),
        ("Planta1/L1/_informative", "informative", ["A"]),
    ])
    assert len(tree) == 1
    assert tree[0]["segment"] == "Planta1"
    assert [c["segment"] for c in tree[0]["children"]] == ["L1", "L2"]


def test_build_tree_empty_input_returns_empty_list():
    assert build_tree([]) == []
