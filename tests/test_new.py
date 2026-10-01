from pathlib import Path

from bot import config, new

CONFIG = Path(__file__).parent.parent / "bot" / "config.toml"


def wizard(tmp_path, answers, **kw):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(CONFIG.read_text())
    replies, said = iter(answers), []
    code = new.run(ask=lambda prompt: next(replies), say=said.append, cfg_path=cfg_path, **kw)
    return code, config.load(cfg_path), "\n".join(said)


def test_a_preset_can_replace_the_followed_strategy(tmp_path):
    code, cfg, _ = wizard(tmp_path, ["Mix 25/25/50", "2", "50000", "2026-10-05", "", "", "2", "y"])
    s = cfg.strategies["mix_25_25_50"]
    assert code == 0 and cfg.follow == ("mix_25_25_50",) and s.start_value == 50000 and cfg.start_value == 30000
    assert f"{s.start}" == "2026-10-05" and s.rebalance == "monthly"
    assert [(sl.fund, sl.weight, sl.rule) for sl in s.slices] == [
        ("DBPG.DE", 0.25, "trend"), ("LQQ.PA", 0.25, "trend"), ("SXRM.DE", 0.5, "hold")]
    assert "mix_30_30_40" in cfg.strategies  # the old one stays, for its history
    assert list(tmp_path.glob("config.toml.bak-*"))


def test_custom_weights_must_add_up_and_names_must_be_new(tmp_path):
    answers = ["Mix 30/30/40", "Bonds heavy", "5", "20", "20", "50", "20", "20", "60",
               "", "", "n", "", "3", "1", "y"]
    code, cfg, said = wizard(tmp_path, answers)
    assert code == 0 and "is taken" in said and "add up to 90%" in said and "1 or 2" in said
    assert cfg.follow == ("mix_30_30_40", "bonds_heavy")  # alongside, the default
    s = cfg.strategies["bonds_heavy"]
    assert [sl.weight for sl in s.slices] == [0.2, 0.2, 0.6] and s.rebalance is None


def test_saying_no_saves_nothing(tmp_path):
    code, cfg, _ = wizard(tmp_path, ["Later", "1", "", "", "", "", "", "n"])
    assert code == 1 and "later" not in cfg.strategies and cfg.follow == ("mix_30_30_40",)
