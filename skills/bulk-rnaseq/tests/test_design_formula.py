"""
Tests for SKILL.md > "Step 2: Design Specification" and the related
"Troubleshooting Common Issues > Design Matrix Issues" section: column
renaming for formula compatibility, adjustment-variable ordering, contrast
format, and confounding detection.
"""
import pandas as pd


def test_rename_columns_with_spaces_for_formula_compatibility():
    # FormulaSyntaxError troubleshooting: rename columns with spaces to underscores
    metadata = pd.DataFrame({"subject status": ["treated", "control"]}, index=["S1", "S2"])
    metadata.columns = metadata.columns.str.replace(" ", "_")

    assert list(metadata.columns) == ["subject_status"]
    # Only the column NAME changes -- the underlying data values are untouched,
    # so contrast values like 'non-viral sepsis patient' remain valid.
    assert metadata["subject_status"].tolist() == ["treated", "control"]


def test_design_formula_puts_adjustment_variable_before_variable_of_interest():
    design = "~batch + condition"
    terms = design.lstrip("~").split(" + ")
    assert terms == ["batch", "condition"]
    assert terms.index("batch") < terms.index("condition")


def test_design_formula_uses_string_notation_not_legacy_list():
    # SKILL.md: "ALWAYS use design=... string formula notation, not design_factors"
    design = "~condition"
    assert isinstance(design, str)
    assert design.startswith("~")


def test_contrast_format_is_variable_test_reference():
    contrast = ["condition", "treated", "control"]
    variable, test_level, reference_level = contrast
    assert variable == "condition"
    assert test_level == "treated"
    assert reference_level == "control"


def test_confounding_detected_via_crosstab():
    # "Design matrix is not full rank" troubleshooting: all treated samples in one batch
    metadata = pd.DataFrame(
        {
            "condition": ["treated", "treated", "treated", "control", "control", "control"],
            "batch": ["b1", "b1", "b1", "b2", "b2", "b2"],
        }
    )
    crosstab = pd.crosstab(metadata.condition, metadata.batch)

    # Fully confounded: each condition level appears in exactly one batch
    confounded = bool((crosstab > 0).sum(axis=1).eq(1).all())
    assert confounded is True


def test_no_confounding_when_batches_are_balanced_across_conditions():
    metadata = pd.DataFrame(
        {
            "condition": ["treated", "treated", "control", "control"],
            "batch": ["b1", "b2", "b1", "b2"],
        }
    )
    crosstab = pd.crosstab(metadata.condition, metadata.batch)

    confounded = bool((crosstab > 0).sum(axis=1).eq(1).all())
    assert confounded is False


def test_interaction_term_formula_syntax():
    design = "~group + condition + group:condition"
    terms = design.lstrip("~").split(" + ")
    assert "group:condition" in terms
