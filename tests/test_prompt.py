from millsheet.extract import inline_refs
from millsheet.prompt import SYSTEM_PROMPT
from millsheet.schema import Line, PageResult


def test_every_field_has_a_description_in_the_schema():
    for model in (Line, PageResult):
        for name, f in model.model_fields.items():
            assert f.description, f"{model.__name__}.{name} に説明がありません"


def test_descriptions_survive_ref_inlining():
    s = inline_refs(PageResult.model_json_schema())
    props = s["properties"]["lines"]["items"]["properties"]
    assert "丸数字" in props["circle_status"]["description"]
    assert "印字どおり" in props["size_raw"]["description"]
    assert "押印" in s["properties"]["stamp_valid_qty"]["description"]


def test_prompt_states_purpose_instead_of_a_role():
    assert not SYSTEM_PROMPT.startswith("あなたは")
    assert "現場で使った本数" in SYSTEM_PROMPT


def test_prompt_keeps_the_rules_of_spec_6_2():
    for rule in ("※下記出荷員数のみ有効", "推測で埋めない", "circle_status=\"なし\"", "カンマ", "判定しない"):
        assert rule in SYSTEM_PROMPT, rule
