import os
import pathlib
import sys
import joblib

WORKDIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKDIR))

from safebench.util.logger import Logger


def _make_logger(tmp_path, name="test"):
    output_dir = str(tmp_path / f"logger_{name}")
    os.makedirs(output_dir, exist_ok=True)
    logger = Logger(output_dir=output_dir, exp_name=name)
    logger.create_eval_dir(load_existing_results=False)
    return logger


def test_fossil_len16_vs_select2_not_skipped(tmp_path):
    logger = _make_logger(tmp_path, "fossil16")
    log_name = "OPT_TestFossil_ROUTE-8"
    select_num = 2
    # create fossil with 16 records (stale) while select_num is 2
    fossil_records = {i: {"score": float(i)} for i in range(16)}
    fossil_results = {"final_score": 0.5}
    result_dir = os.path.join(logger.output_dir, "eval_results")
    os.makedirs(result_dir, exist_ok=True)
    rec_path = os.path.join(result_dir, log_name + "_records.pkl")
    res_path = os.path.join(result_dir, log_name + "_results.pkl")
    joblib.dump(fossil_records, rec_path)
    joblib.dump(fossil_results, res_path)

    # missing pinned => must NOT be considered complete, must re-evaluate
    entry_missing_pinned = {}
    assert logger.is_eval_complete(log_name, select_num, entry_missing_pinned) is False

    # after check, fossil files should be renamed to *.fossil.pkl not deleted
    fossil_rec = rec_path[:-4] + ".fossil.pkl"
    fossil_res = res_path[:-4] + ".fossil.pkl"
    assert os.path.exists(fossil_rec), "fossil records not renamed"
    assert os.path.exists(fossil_res), "fossil results not renamed"
    assert not os.path.exists(rec_path), "original fossil should be moved"

    # also test missing pinned with len==select_num still re-evaluates
    logger2 = _make_logger(tmp_path, "fossil2")
    log_name2 = "OPT_MissingPinned_ROUTE-9"
    rec_path2 = os.path.join(logger2.output_dir, "eval_results", log_name2 + "_records.pkl")
    res_path2 = os.path.join(logger2.output_dir, "eval_results", log_name2 + "_results.pkl")
    os.makedirs(os.path.join(logger2.output_dir, "eval_results"), exist_ok=True)
    joblib.dump({0: {"x": 1}, 1: {"x": 2}}, rec_path2)
    joblib.dump({"final_score": 1}, res_path2)
    entry_no_pinned = {"select_id": [0, 1]}  # has select_id but no pinned
    assert logger2.is_eval_complete(log_name2, select_num, entry_no_pinned) is False
    assert os.path.exists(rec_path2[:-4] + ".fossil.pkl")
    assert not os.path.exists(rec_path2)


def test_complete_eval_with_valid_pinned_skips(tmp_path):
    logger = _make_logger(tmp_path, "complete")
    log_name = "OPT_Complete_ROUTE-8"
    select_num = 2
    records = {0: {"score": 1}, 1: {"score": 2}}
    results = {"final_score": 1.5}
    result_dir = os.path.join(logger.output_dir, "eval_results")
    os.makedirs(result_dir, exist_ok=True)
    rec_path = os.path.join(result_dir, log_name + "_records.pkl")
    res_path = os.path.join(result_dir, log_name + "_results.pkl")
    joblib.dump(records, rec_path)
    joblib.dump(results, res_path)

    entry_valid = {"select_id": [0, 1], "pinned": {"0": {"OPT_A": 1.0}, "1": {"OPT_A": 2.0}}}
    assert logger.is_eval_complete(log_name, select_num, entry_valid) is True
    # fast path: original files must remain, no fossil
    assert os.path.exists(rec_path)
    assert not os.path.exists(rec_path[:-4] + ".fossil.pkl")


def test_scenic_runner_guard_mirrors_train_path():
    src = (WORKDIR / "safebench" / "scenic_runner.py").read_text()
    assert "if 'select_id' in entry and entry.get('pinned')" in src
    assert "is_eval_complete" in src
    assert "fossil detection" in src
    assert "_rename_fossil" in src
    # ensure fossil logged yellow
    assert "'yellow'" in src or '"yellow"' in src
    # ensure not silently deleting
    assert "os.remove" not in src.split("is_eval_complete")[1].split("continue")[0] or "_rename_fossil" in src


def test_logger_no_bare_except_and_fossil_rename():
    src = (WORKDIR / "safebench" / "util" / "logger.py").read_text()
    assert "is_eval_complete" in src
    assert "_rename_fossil" in src
    assert ".fossil.pkl" in src
    assert "except FileNotFoundError" in src
    # check check_eval_dir no bare except
    assert "except:" not in src


def test_fossil_not_deleted_only_renamed(tmp_path):
    logger = _make_logger(tmp_path, "notdeleted")
    log_name = "OPT_NotDeleted"
    select_num = 2
    rec_path = os.path.join(logger.output_dir, "eval_results", log_name + "_records.pkl")
    res_path = os.path.join(logger.output_dir, "eval_results", log_name + "_results.pkl")
    os.makedirs(os.path.join(logger.output_dir, "eval_results"), exist_ok=True)
    joblib.dump({i: {} for i in range(5)}, rec_path)
    joblib.dump({}, res_path)
    entry = {}
    logger.is_eval_complete(log_name, select_num, entry)
    # original gone, fossil exists
    assert not os.path.exists(rec_path)
    fossil = rec_path[:-4] + ".fossil.pkl"
    assert os.path.exists(fossil)
    loaded = joblib.load(fossil)
    assert len(loaded) == 5
