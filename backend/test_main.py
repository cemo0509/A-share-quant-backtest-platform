"""后端API测试"""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_check():
    """测试健康检查端点"""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_strategies():
    """测试获取策略列表"""
    response = client.get("/api/strategy/list")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["data"]) > 0


def test_data_cache():
    """测试数据缓存列表"""
    response = client.get("/api/data/cache")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


if __name__ == "__main__":
    # 运行测试
    test_health_check()
    test_get_strategies()
    test_data_cache()
    print("所有测试通过!")
