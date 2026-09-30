from pathlib import Path


def _template() -> str:
    return Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")


def _nav_script() -> str:
    return Path("static/js/master-data-nav.js").read_text(encoding="utf-8")


def _model_block() -> str:
    """صف الطراز يرسمه ماكرو واحد في القالب، فال slice يتبع علامتيه."""
    template = _template()
    start = template.index("{% macro model_block(m, t) %}")
    return template[start:template.index("{% endmacro %}", start)]


def test_model_navigation_has_nested_tire_branch():
    block = _model_block()
    tire = block.index('data-section="tires"')
    sizes = block.index('data-section="sizes"', tire)
    batteries = block.index('data-section="batteries"', sizes)
    assert sizes < batteries
    assert 'class="children"' in block[tire:batteries]


def test_model_navigation_keeps_every_editor_section_under_the_model():
    block = _model_block()
    for section in ("basic", "tires", "sizes", "batteries", "specs"):
        assert f'data-section="{section}"' in block
    # المواضع صارت ناتج التوزيع على المحاور، فلا قسم لها في التنقل ولا محرر لها.
    assert 'data-section="positions"' not in block
    # قسمان قابلان للاندماج: أقسام الطراز نفسها، ثم المقاسات داخل الإطارات.
    assert block.count('class="children') >= 2
    assert 'class="children model-sections"' in block


def test_categories_are_sheet_headings_with_types_and_models_nested_under_each():
    template = _template()
    assert "{% macro type_block(t, sheet_type) %}" in template
    assert "{% macro model_block(m, t) %}" in template
    assert "{% for c in categories if not c.is_system %}" in template
    assert "types|selectattr('category_id','equalto',c.id)|list" in template
    assert "models|selectattr('equipment_type_id','equalto',t.id)|list" in template
    assert "{{ type_block(t, 'category') }}" in template
    assert "{{ model_block(m, t) }}" in template
    # شريحة مستقلة لكل فئة، ورأسها زر يدمجها ويفردها.
    assert 'class="tree-group mdx-sheet open"' in template
    assert 'class="sheet-head"' in template
    assert 'data-expand="1"' in template
    assert 'class="children sheet-body"' in template


def test_navigation_no_longer_renders_the_flat_tree():
    template = _template()
    for gone in (
        'class="tree-card"',
        'id="tree"',
        'class="tree-search"',
        'class="master-reference-block"',
        'data-library-root="private"',
        'data-ref="private-categories"',
        'id="tree-toast"',
    ):
        assert gone not in template, f"بقايا الشجرة في التنقل: {gone}"
    for current in (
        'id="nav"',
        'id="navSearch"',
        'id="nav-toast"',
        'id="btn-nav-expand-all"',
        'id="btn-nav-collapse-all"',
    ):
        assert current in template


def test_reference_creation_actions_cover_every_level():
    template = _template()
    # الفئة: زر الصفحة الرئيسي (الشجرة القديمة كانت تضع ＋ داخلها)
    assert 'id="btn-add-root-category"' in template
    # النوع: داخل شريحة الفئة
    assert 'data-add="type"' in template
    assert 'data-new-ref="type"' in template
    assert 'data-new-type-for-category="{{ c.id }}"' in template
    # الطراز: داخل صف النوع
    assert 'data-add="model"' in template
    assert 'data-new-ref="model"' in template
    assert 'data-new-model-for-type="{{ t.id }}"' in template
    # العلامة والخاصية يبقيان في الشريط العلوي فقط
    assert 'data-add="brand"' not in template
    assert 'data-add="spec"' not in template
    assert 'id="newModelTop"' not in template
    assert 'id="importExcelBtn"' not in template


def test_model_row_exposes_its_own_actions():
    template = _template()
    assert 'data-copy="{{ m.id }}"' in template
    assert 'data-delete="{{ m.id }}"' in template
    assert 'data-edit="{{ m.id }}"' in template
    script = _nav_script()
    assert "postDelete(`/equipment-types/models/${encodeURIComponent(del.dataset.delete)}/delete`" in script
    assert "window.editModel(edit.dataset.edit)" in script
    assert "copyModel(copy.dataset.copy)" in script


def test_click_handler_resolves_inline_actions_then_toggles_then_rows():
    handler = _nav_script().split("nav.addEventListener('click'", 1)[1]
    order = [
        "const action = event.target.closest('[data-add],[data-new-ref]')",
        "const position = event.target.closest('[data-tree-add]')",
        "const copy = event.target.closest('[data-copy]')",
        "const del = event.target.closest('[data-delete]')",
        "const edit = event.target.closest('[data-edit]')",
        "const toggle = event.target.closest('.tree-toggle')",
        "const expand = event.target.closest('[data-expand]')",
        "const row = event.target.closest('[data-model-row]')",
        "const model = event.target.closest('[data-model]')",
        "const ref = event.target.closest('[data-ref-item]')",
    ]
    positions = [handler.index(fragment) for fragment in order]
    assert positions == sorted(positions)
    assert "group.classList.toggle('open')" in handler[positions[5]:positions[6]]


def test_inline_tire_add_action_loads_the_model_then_adds_a_size_row():
    block = _model_block()
    assert 'data-tree-add="size"' in block
    assert '＋ مقاس' in block
    # قرار المستخدم (2026-09-30): المواضع ناتج التوزيع، فلا زرّ لإضافة صف موضع.
    assert 'data-tree-add="position"' not in block
    assert '＋ موضع' not in block
    script = _nav_script()
    assert "window.editModel(targetModel.dataset.model, 'tires')" in script
    assert "window.addSize()" in script
    assert "addPos" not in script
