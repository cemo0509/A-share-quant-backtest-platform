"""数据可靠性金标准（P0-3 / P0-4 / P0-5 / F-07）。

- 模拟数据禁止落盘：假数据一旦落盘会「永久占坑」，网络恢复也拿不到真数据
- 缓存必须完全覆盖请求区间才命中：部分覆盖会静默截断区间
- 缓存键必须含复权方式：qfq/hfq/raw 数据不同，混用会算错收益
"""
import pandas as pd

import core.data_loader as dl
from conftest import cleanup_cache, make_wave_df


class TestMockData:
    def test_mock_never_written_to_cache(self, monkeypatch):
        """模拟数据禁止落盘 + is_mock 标记不丢（切片后仍在）。"""
        sym = "__MK__"
        df = make_wave_df()
        df.attrs["is_mock"] = True
        monkeypatch.setattr(dl, "_fetch_from_akshare", lambda *a: df)
        try:
            out = dl.fetch_kline(sym, "20230101", "20241231",
                                 period="daily", adjust="qfq")
            assert out.attrs.get("is_mock") is True, "mock 标记丢失"
            assert not dl._cache_path(sym, "daily", "qfq").exists(), \
                "模拟数据被写入缓存（假数据永久占坑）"
        finally:
            cleanup_cache(sym)


class TestCacheCoverage:
    def test_covers_requires_full_range(self):
        """部分覆盖不得当完全覆盖。"""
        df = make_wave_df(n=100, start="2023-01-02")  # 约覆盖到 2023-05-19
        assert dl._covers(df, "20230103", "20230510") is True
        assert dl._covers(df, "20230101", "20241231") is False
        assert dl._covers(df, "20230601", "20241231") is False

    def test_partial_cache_not_treated_as_full(self, monkeypatch):
        """预置部分缓存时，必须增量拉取补全而非截断返回。"""
        sym = "__PC__"
        full = make_wave_df(n=400)
        cleanup_cache(sym)
        path = dl._cache_path(sym, "daily", "qfq")
        path.parent.mkdir(parents=True, exist_ok=True)
        full.iloc[:100].to_parquet(path, index=False)
        monkeypatch.setattr(dl, "_fetch_from_akshare", lambda *a: full)
        try:
            out = dl.fetch_kline(sym, "20230101", "20241231",
                                 period="daily", adjust="qfq")
            assert len(out) == 400, \
                f"部分缓存被当完全覆盖，区间被截断为 {len(out)} 行"
        finally:
            cleanup_cache(sym)


class TestCacheKey:
    def test_cache_path_includes_adjust(self):
        """缓存键必须含复权方式：不同复权口径不能共用文件。"""
        qfq = dl._cache_path("X", "daily", "qfq")
        hfq = dl._cache_path("X", "daily", "hfq")
        assert qfq != hfq
        assert "qfq" in qfq.name and "hfq" in hfq.name

    def test_adjust_param_passed_through(self, monkeypatch):
        """复权方式必须透传到数据源（此前恒为 qfq，用户无法对比口径）。"""
        sym = "__ADJ__"
        seen = {}

        def spy(s, a, b, c, d):
            seen["adjust"] = d
            return make_wave_df()

        monkeypatch.setattr(dl, "_fetch_from_akshare", spy)
        try:
            dl.fetch_kline(sym, "20230101", "20241231", period="daily", adjust="hfq")
            assert seen.get("adjust") == "hfq"
        finally:
            cleanup_cache(sym)
