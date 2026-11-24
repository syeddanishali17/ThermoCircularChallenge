from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from thermocircular.ui import PAGES


def button(app, label):
    return next(item for item in app.button if item.label == label)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("TC_LOCAL_STORAGE", raising=False)
    return AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=45).run()


@pytest.mark.parametrize("language", ("English", "Deutsch"))
def test_all_pages(app, language):
    app.selectbox(key="language").set_value(language).run()
    for page in PAGES:
        navigation = app.selectbox(key="section_picker") if language == "English" else app.radio(key="nav")
        navigation.set_value(page).run()
        assert not app.exception, (page, [item.message for item in app.exception])
        assert app.radio(key="nav").value == app.selectbox(key="section_picker").value == page


def test_custom_run_compare_save_reopen_reset(app):
    button(app, "Open scenario lab").click().run()
    assert app.radio(key="nav").value == "Scenario lab"
    app.selectbox(key="preset_choice").set_value("Pipe route 3 km").run()
    assert app.warning
    button(app, "Run simulation").click().run()
    assert not app.exception
    assert app.session_state["custom_run"].d["modules"] == 0
    name = next(item for item in app.text_input if item.label == "Scenario name")
    name.set_value("Pipe test")
    button(app, "Save current result").click().run()
    assert app.session_state["scenario_store"].list()[0][1] == "Pipe test"
    saved_key = app.session_state["scenario_store"].list()[0][0]
    next(item for item in app.multiselect if item.label == "Compare up to four saved scenarios").select(saved_key).run()
    assert any("Pipe test" in item.value.get("Scenario", []).tolist()
               for item in app.dataframe if "Scenario" in item.value)
    button(app, "Reset to baseline").click().run()
    assert app.session_state["custom_run"] is None
    button(app, "Open saved scenario").click().run()
    assert app.session_state["custom_run"].settings.pipe_km == 3
    app.radio(key="nav").set_value("Evidence & exports").run()
    assert not app.exception
    assert len(app.get("download_button")) >= 8
    app.selectbox(key="section_picker").set_value("Scenario lab").run()
    button(app, "Delete").click().run()
    assert app.error
    assert app.session_state["scenario_store"].list()
    next(item for item in app.checkbox if item.label.startswith("Confirm deletion")).check()
    button(app, "Delete").click().run()
    assert not app.exception
    assert not app.session_state["scenario_store"].list()


def test_project_story_keeps_baseline_after_scenario_change(app):
    button(app, "Winter price stress").click().run()
    assert app.session_state["custom_run"] is not None
    app.selectbox(key="section_picker").set_value("Overview").run()
    assert "The challenge" in [item.value for item in app.subheader]
    summary = next(item.value for item in app.markdown if "audited baseline" in item.value)
    assert all(number in summary for number in ("27.63", "+0.36", "10.18", "2.01"))

    app.selectbox(key="language").set_value("Deutsch").run()
    assert "Die Herausforderung" in [item.value for item in app.subheader]
    summary = next(item.value for item in app.markdown if "geprüften Referenz" in item.value)
    assert all(number in summary for number in ("27,63", "+0,36", "10,18", "2,01"))


def test_custom_failure_preserves_baseline(app):
    app.radio(key="nav").set_value("Scenario lab").run()
    app.number_input(key="cop_0").set_value(1.)
    button(app, "Run simulation").click().run()
    assert not app.exception
    assert app.error
    assert "custom_run" not in app.session_state


def test_jury_six_steps(app):
    app.radio(key="nav").set_value("Jury mode").run()
    for step in range(1, 6):
        button(app, "Next").click().run()
        assert app.session_state["jury_step"] == step
        assert not app.exception
    button(app, "Restart pitch at baseline").click().run()
    assert app.session_state["jury_step"] == 0


def test_stress_sensitivity_and_hourly_bundle(app):
    button(app, "Winter price stress").click().run()
    assert not app.exception
    assert app.session_state["custom_run"].settings.expensive_hours == 320
    app.radio(key="nav").set_value("Investment").run()
    button(app, "Run one-way sensitivity").click().run()
    button(app, "Run tariff × distance grid").click().run()
    assert not app.exception
    assert len(app.session_state["sweep_grid"][3]) == 7
    app.radio(key="nav").set_value("Evidence & exports").run()
    button(app, "Run 21-case stress suite on current inputs").click().run()
    assert not app.exception
    assert len(app.session_state["stress_result"][1]) == 21
    button(app, "Prepare all seven hourly traces (ZIP)").click().run()
    assert not app.exception
    assert len(app.session_state["hourly_bundle"][1]) > 100_000


def test_preset_and_animation_state(app):
    button(app, "Pause campus animation").click().run()
    assert button(app, "Play campus animation")
    button(app, "Winter price stress").click().run()
    assert app.selectbox(key="heat_case").value == "D"
    app.selectbox(key="section_picker").set_value("Scenario lab").run()
    assert app.selectbox(key="preset_choice").value == "High winter price"
    button(app, "Run simulation").click().run()
    assert any("Simulation complete" in notice.value for notice in app.success)
    app.selectbox(key="section_picker").set_value("Overview").run()
    assert button(app, "Play campus animation")
