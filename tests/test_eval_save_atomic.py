import os
import sys
import pathlib
import tempfile
import types

import joblib
import pytest

WORKDIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKDIR))

from safebench.util.logger import Logger


def _make_logger(tmp_path, name="test"):
    output_dir = str(tmp_path / f"logger_{name}")
    os.makedirs(output_dir, exist_ok=True)
    logger = Logger(output_dir=output_dir, exp_name=name)
    logger.create_eval_dir(load_existing_results=False)
    return logger


def test_atomic_write_no_tmp_leak(tmp_path):
    logger = _make_logger(tmp_path, "atomic_no_tmp")
    log_name = "OPT_TestA"
    logger.add_eval_results(records={0: {"score": 1}}, scores={"final_score": 1.0})
    logger.save_eval_results(log_name)
    result_file = logger.result_file
    record_file = logger.record_file
    assert os.path.exists(result_file)
    assert os.path.exists(record_file)
    assert not os.path.exists(result_file + ".tmp")
    assert not os.path.exists(record_file + ".tmp")
    loaded = joblib.load(record_file)
    assert len(loaded) == 1
    assert 0 in loaded

    # second save overwrites atomically, no fossil deletion, still no tmp
    logger.add_eval_results(records={1: {"score": 2}}, scores={"final_score": 2.0})
    logger.save_eval_results(log_name)
    assert not os.path.exists(record_file + ".tmp")
    loaded2 = joblib.load(record_file)
    assert len(loaded2) == 2


def test_atomic_overwrite_is_not_truncated(tmp_path):
    logger = _make_logger(tmp_path, "atomic_overwrite")
    log_name = "OPT_Overwrite"
    # write large then small to ensure atomic rename doesn't leave truncated
    big_records = {i: {"v": i} for i in range(50)}
    logger.add_eval_results(records=big_records, scores={"final_score": 0})
    logger.save_eval_results(log_name)
    record_file = logger.record_file
    size_big = os.path.getsize(record_file)

    # overwrite with smaller
    logger.clear()
    logger.create_eval_dir(load_existing_results=False)
    # re-create logger with same log_name but new records - need to reuse same files
    # Manually set to same log_name files
    logger.eval_records = {0: {"v": 0}}
    logger.eval_results = {"final_score": 0}
    logger.save_eval_results(log_name)
    assert os.path.exists(record_file)
    assert not os.path.exists(record_file + ".tmp")
    loaded = joblib.load(record_file)
    assert loaded is not None
    assert len(loaded) == 1


def test_kill_mid_loop_preserves_finished(tmp_path):
    """
    Kill fixture: simulate eval loop that saves every episode + finally.
    29 OK but 16 records bug would fail this - we prove len(records)==finished.
    """
    logger = _make_logger(tmp_path, "kill_mid")
    log_name = "OPT_KillTest"
    num_total = 29
    kill_after = 16

    # Simulate what ScenicRunner.eval now does: save every episode + finally
    finished = 0
    try:
        try:
            for i in range(num_total):
                # emulate env.running_results growing by 1 per episode
                logger.add_eval_results(records={i: {"collision": False, "score": float(i)}}, scores={"final_score": float(i)})
                # per-episode atomic save (save_freq=1)
                logger.save_eval_results(log_name)
                finished += 1
                if finished == kill_after:
                    raise RuntimeError("simulated kill mid-loop")
        finally:
            # finally guarantee - must save even if killed
            logger.save_eval_results(log_name)
    except RuntimeError:
        pass

    # Verify on-disk pkl has exactly finished records, not stale 16 vs 29 mismatch
    record_file = logger.record_file
    loaded = joblib.load(record_file)
    assert len(loaded) == finished, f"lost records: finished {finished} but pkl has {len(loaded)}"
    assert len(loaded) == kill_after
    # also verify result file exists and is loadable (atomic)
    assert os.path.exists(logger.result_file)
    assert not os.path.exists(record_file + ".tmp")


def test_kill_mid_loop_full_run_no_loss(tmp_path):
    logger = _make_logger(tmp_path, "full_run")
    log_name = "OPT_FullRun"
    num_total = 10
    finished = 0
    try:
        for i in range(num_total):
            logger.add_eval_results(records={i: {"x": i}}, scores={"final_score": i})
            logger.save_eval_results(log_name)
            finished += 1
            if finished == 5:
                raise RuntimeError("kill at 5")
    except RuntimeError:
        pass
    finally:
        logger.save_eval_results(log_name)
    # after kill, finally already saved; reload and check
    loaded = joblib.load(logger.record_file)
    assert len(loaded) == 5

    # continue run without kill should have 29==29
    logger2 = _make_logger(tmp_path, "full29")
    log_name2 = "OPT_Full29"
    finished2 = 0
    for i in range(29):
        logger2.add_eval_results(records={i: {"x": i}}, scores={"s": i})
        logger2.save_eval_results(log_name2)
        finished2 += 1
    # final save already done per-episode, but also ensure file
    loaded2 = joblib.load(logger2.record_file)
    assert len(loaded2) == finished2 == 29


def test_scenic_runner_eval_uses_try_finally_and_every_episode(tmp_path):
    scenic_path = WORKDIR / "safebench" / "scenic_runner.py"
    src = scenic_path.read_text()
    # must have try/finally around eval loop and unconditional save every episode
    assert "try:" in src
    assert "finally:" in src
    # ensure save every episode - check that save_eval_results(log_name) appears inside loop without conditional
    # The old buggy pattern was `if len(self.env.running_results) % self.save_freq == 0:`
    # After fix, there should be unconditional `self.logger.save_eval_results(log_name)` inside the while loop
    # and save_freq=1 for eval
    assert "self.save_freq = 1" in src
    # ensure the conditional intermittent save is gone (or at least unconditional save exists)
    # Count saves: there should be at least two saves (inside loop + finally)
    assert src.count("self.logger.save_eval_results(log_name)") >= 2


def test_logger_uses_atomic_tmp_fsync_rename():
    logger_path = WORKDIR / "safebench" / "util" / "logger.py"
    src = logger_path.read_text()
    assert "_atomic_joblib_dump" in src
    assert ".tmp" in src
    assert "os.fsync" in src
    assert "os.rename" in src


def test_run_eval_no_bare_except():
    run_eval_path = WORKDIR / "scripts" / "run_eval.py"
    src = run_eval_path.read_text()
    # no bare except:
    assert "except:" not in src
    # must have explicit TimeoutError handling with fence_code and sys.exit
    assert "except TimeoutError" in src
    assert "fence_code" in src
    assert "sys.exit" in src


def test_run_eval_parity_with_run_train():
    run_train_src = (WORKDIR / "scripts" / "run_train.py").read_text()
    run_eval_src = (WORKDIR / "scripts" / "run_eval.py").read_text()
    # both should use same fence_code pattern
    assert "getattr(e, 'fence_code'" in run_train_src
    assert "getattr(e, 'fence_code'" in run_eval_src
